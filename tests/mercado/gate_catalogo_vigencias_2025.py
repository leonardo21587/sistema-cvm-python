from __future__ import annotations

import csv
import sys
from pathlib import Path

import duckdb


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.catalogo import carregar_catalogo_referencia  # noqa: E402
from src.mercado.catalogo_vigencias import (  # noqa: E402
    EvidenciaFcaTicker,
    ObservacaoIsin,
    construir_catalogo_temporal,
)
from src.mercado.identidade import resolver_instrumento  # noqa: E402
from src.mercado.providers.b3_cotahist import iterar_cotacoes  # noqa: E402
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
)
from src.mercado.schema import criar_schema_identidade  # noqa: E402


REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
SAIDA_DIR = REPORTS_DIR / "catalogo_temporal_2025"

INSTRUMENTOS_ATUAIS = REFERENCE_DIR / "instrumentos.csv"
TICKERS_ATUAIS = REFERENCE_DIR / "tickers_historico.csv"
IDENTIFICADORES_ATUAIS = REFERENCE_DIR / "identificadores.csv"

INSTRUMENTOS_CANDIDATOS = (
    REPORTS_DIR / "catalogo_ampliado_instrumentos_2025.csv"
)
ALOCACOES = REPORTS_DIR / "catalogo_ampliado_alocacoes_2025.csv"
RECONCILIADOS = REPORTS_DIR / "universo_2025_reconciliado_tickers.csv"

ANOS_FCA = tuple(range(2010, 2027))


def _ler(caminho: Path, delimitador: str) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=delimitador))


def _escrever(
    caminho: Path,
    linhas: list[dict[str, str]],
    campos: list[str],
    delimitador: str = ",",
) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=campos,
            delimiter=delimitador,
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def _tickers_alvo(
    reconciliados: list[dict[str, str]],
) -> set[str]:
    return {
        linha["TICKER"].strip().upper()
        for linha in reconciliados
        if not linha["PROBLEMAS"].strip()
        and linha["STATUS_FINAL"].strip().upper()
        != "FORA_UNIVERSO_SISTEMA"
    }


def _carregar_fca(
    tickers_alvo: set[str],
) -> tuple[list[EvidenciaFcaTicker], list[tuple[int, int]]]:
    evidencias = []
    ambiguidades = []

    for ano in ANOS_FCA:
        caminho = baixar_fca(ano)
        registros, ambiguos = ler_fca_valores_mobiliarios(
            caminho,
            ano=ano,
        )
        ambiguidades.append((ano, len(ambiguos)))

        for registro in registros:
            ticker = registro.codigo_negociacao.strip().upper()
            if ticker not in tickers_alvo:
                continue
            if not registro.cd_cvm:
                continue

            evidencias.append(
                EvidenciaFcaTicker(
                    ano=ano,
                    ticker=ticker,
                    cd_cvm=registro.cd_cvm,
                    data_referencia=registro.data_referencia,
                    versao=registro.versao,
                    data_inicio_negociacao=registro.data_inicio_negociacao,
                    data_fim_negociacao=registro.data_fim_negociacao,
                    data_inicio_listagem=registro.data_inicio_listagem,
                    data_fim_listagem=registro.data_fim_listagem,
                )
            )

    return evidencias, ambiguidades


def _observacoes_isin(
    caminhos: dict[int, Path],
    tickers_alvo: set[str],
) -> list[ObservacaoIsin]:
    observacoes = []

    for ano, caminho in caminhos.items():
        if not caminho.is_file():
            raise FileNotFoundError(caminho)

        for cotacao in iterar_cotacoes(caminho):
            if cotacao.data.year != ano:
                raise RuntimeError(
                    f"{caminho.name}: registro {cotacao.data} fora de {ano}."
                )
            if cotacao.tipo_mercado != "010":
                continue
            if cotacao.ticker not in tickers_alvo:
                continue
            if not cotacao.isin:
                continue

            observacoes.append(
                ObservacaoIsin(
                    data=cotacao.data,
                    ticker=cotacao.ticker,
                    isin=cotacao.isin,
                )
            )

    return observacoes


def _catalogo_cvm() -> set[str]:
    con = conectar_cvm(read_only=True)
    try:
        return {
            str(linha[0]).strip().zfill(6)
            for linha in con.execute(
                "SELECT CD_CVM FROM empresas"
            ).fetchall()
        }
    finally:
        con.close()


def _validar_runtime(
    *,
    saida_dir: Path,
    reconciliados: list[dict[str, str]],
    alocacoes: list[dict[str, str]],
) -> list[str]:
    falhas = []

    con = duckdb.connect(":memory:")
    try:
        criar_schema_identidade(con)
        carregar_catalogo_referencia(
            con,
            reference_dir=saida_dir,
        )

        por_chave = {
            linha["CHAVE_CANDIDATO"].strip():
                int(linha["INSTRUMENTO_ID"])
            for linha in alocacoes
        }

        for linha in reconciliados:
            if linha["PROBLEMAS"].strip():
                continue
            if (
                linha["STATUS_FINAL"].strip().upper()
                == "FORA_UNIVERSO_SISTEMA"
            ):
                continue

            chave = (
                f"{linha['CD_CVM'].strip().zfill(6)}|"
                f"{linha['TIPO_ATIVO'].strip().upper()}|"
                f"{linha['CLASSE'].strip().upper()}"
            )
            esperado = por_chave[chave]
            ticker = linha["TICKER"].strip().upper()

            for campo in ("PRIMEIRA_DATA_2025", "ULTIMA_DATA_2025"):
                data_ref = linha[campo]
                resolvido = resolver_instrumento(
                    con,
                    bolsa="B3",
                    ticker=ticker,
                    data_referencia=data_ref,
                )
                if resolvido != esperado:
                    falhas.append(
                        f"{ticker}|{data_ref}: "
                        f"{resolvido} != {esperado}"
                    )
    finally:
        con.close()

    return falhas


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Uso: python tests/mercado/gate_catalogo_vigencias_2025.py "
            "<COTAHIST_A2024.ZIP> <COTAHIST_A2025.ZIP>"
        )

    cotahist = {
        2024: Path(sys.argv[1]),
        2025: Path(sys.argv[2]),
    }

    instrumentos_atuais = _ler(INSTRUMENTOS_ATUAIS, ",")
    tickers_atuais = _ler(TICKERS_ATUAIS, ",")
    identificadores_atuais = _ler(IDENTIFICADORES_ATUAIS, ",")
    instrumentos_candidatos = _ler(INSTRUMENTOS_CANDIDATOS, ",")
    alocacoes = _ler(ALOCACOES, ";")
    reconciliados = _ler(RECONCILIADOS, ";")

    alvo = _tickers_alvo(reconciliados)

    print("=" * 100)
    print("SISTEMA CVM — D.4 — GATE DO CATÁLOGO TEMPORAL 2025")
    print("=" * 100)
    print(f"Tickers 2025 ligados ao Sistema CVM: {len(alvo):,}")
    print("Lendo FCA 2010–2026 para vigências de ticker...")

    evidencias_fca, ambiguidades_fca = _carregar_fca(alvo)

    print(
        f"Evidências FCA pertinentes: {len(evidencias_fca):,}"
    )
    print(
        "CNPJ ambíguos por arquivo FCA: "
        + ", ".join(
            f"{ano}={qtd}"
            for ano, qtd in ambiguidades_fca
            if qtd
        )
        if any(qtd for _, qtd in ambiguidades_fca)
        else "CNPJ ambíguos por arquivo FCA: nenhum"
    )
    print("Lendo COTAHIST 2024–2025 para vigências observadas de ISIN...")

    observacoes = _observacoes_isin(cotahist, alvo)
    print(f"Observações ticker/data/ISIN: {len(observacoes):,}")
    print()

    resultado = construir_catalogo_temporal(
        instrumentos_existentes=instrumentos_atuais,
        instrumentos_candidatos=instrumentos_candidatos,
        tickers_existentes=tickers_atuais,
        identificadores_existentes=identificadores_atuais,
        alocacoes=alocacoes,
        tickers_reconciliados_2025=reconciliados,
        evidencias_fca=evidencias_fca,
        observacoes_isin=observacoes,
    )

    _escrever(
        SAIDA_DIR / "instrumentos.csv",
        resultado.instrumentos,
        [
            "INSTRUMENTO_ID",
            "CD_CVM",
            "TIPO_ATIVO",
            "CLASSE",
            "MOEDA",
            "DT_INICIO",
            "DT_FIM",
            "STATUS",
            "FONTE",
        ],
    )
    _escrever(
        SAIDA_DIR / "tickers_historico.csv",
        resultado.tickers,
        [
            "INSTRUMENTO_ID",
            "BOLSA",
            "TICKER",
            "DT_INICIO",
            "DT_FIM",
            "STATUS",
            "FONTE",
        ],
    )
    _escrever(
        SAIDA_DIR / "identificadores.csv",
        resultado.identificadores,
        [
            "INSTRUMENTO_ID",
            "TIPO_IDENTIFICADOR",
            "VALOR",
            "DT_INICIO",
            "DT_FIM",
            "FONTE",
        ],
    )
    _escrever(
        SAIDA_DIR / "mapa_tickers_2025.csv",
        resultado.mapa_tickers_2025,
        [
            "TICKER",
            "INSTRUMENTO_ID",
            "ORIGEM_VIGENCIA",
            "DT_INICIO",
            "DT_FIM",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
        ],
        ";",
    )
    _escrever(
        SAIDA_DIR / "revisao.csv",
        resultado.revisao,
        ["NIVEL", "CHAVE", "DETALHE"],
        ";",
    )

    runtime = []
    if resultado.gate_aprovado:
        runtime = _validar_runtime(
            saida_dir=SAIDA_DIR,
            reconciliados=reconciliados,
            alocacoes=alocacoes,
        )

    catalogo_cvm = _catalogo_cvm()
    cd_ausentes = sorted({
        linha["CD_CVM"]
        for linha in resultado.instrumentos
        if linha["CD_CVM"] not in catalogo_cvm
    })

    ids_antes = {
        int(x["INSTRUMENTO_ID"])
        for x in instrumentos_atuais
    }
    ids_depois = {
        int(x["INSTRUMENTO_ID"])
        for x in resultado.instrumentos
    }
    ids_preservados = ids_antes.issubset(ids_depois)

    origens = {}
    for linha in resultado.mapa_tickers_2025:
        origem = linha["ORIGEM_VIGENCIA"]
        origens[origem] = origens.get(origem, 0) + 1

    gate = (
        resultado.gate_aprovado
        and not runtime
        and not cd_ausentes
        and ids_preservados
        and len(resultado.instrumentos) == 380
        and len(resultado.mapa_tickers_2025) == 389
    )

    print("RESUMO")
    print("-" * 100)
    print(f"Instrumentos candidatos: {len(resultado.instrumentos):,}")
    print(f"Vigências de ticker: {len(resultado.tickers):,}")
    print(f"Identificadores/ISIN: {len(resultado.identificadores):,}")
    print(
        "Tickers 2025 com mapeamento temporal: "
        f"{len(resultado.mapa_tickers_2025):,}"
    )
    print(f"Revisões estruturais: {len(resultado.revisao):,}")
    print(f"Falhas de resolução runtime: {len(runtime):,}")
    print(f"CD_CVM ausentes das 499 empresas: {len(cd_ausentes):,}")
    print(f"IDs antigos preservados: {ids_preservados}")
    print()

    print("ORIGEM DO INÍCIO DAS VIGÊNCIAS 2025")
    print("-" * 100)
    for origem, quantidade in sorted(origens.items()):
        print(f"{origem:38s} | {quantidade:4d}")
    print()

    if resultado.revisao:
        print("REVISÕES — BLOQUEANTES")
        print("-" * 100)
        for item in resultado.revisao[:50]:
            print(
                f"{item['NIVEL']:14s} | "
                f"{item['CHAVE']:28s} | "
                f"{item['DETALHE']}"
            )
        if len(resultado.revisao) > 50:
            print(
                f"... e mais {len(resultado.revisao) - 50} revisão(ões)."
            )
        print()

    if runtime:
        print("FALHAS DE RESOLUÇÃO — BLOQUEANTES")
        print("-" * 100)
        for falha in runtime[:50]:
            print(falha)
        print()

    if cd_ausentes:
        print("CD_CVM AUSENTES — BLOQUEANTES")
        print("-" * 100)
        for cd_cvm in cd_ausentes:
            print(cd_cvm)
        print()

    print(f"Diretório candidato: {SAIDA_DIR}")
    print(f"GATE_APROVADO: {gate}")
    print()

    if gate:
        print("RESULTADO: APROVADO PARA PROMOÇÃO CONTROLADA")
        print(
            "Os CSVs oficiais de referência permanecem intocados. "
            "Não iniciar 2010–2023 ainda; a promoção será a próxima ação."
        )
    else:
        print("RESULTADO: BLOQUEADO")
        raise RuntimeError(
            "Catálogo temporal ainda não pode ser promovido."
        )


if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import BANCO_DUCKDB, conectar as conectar_cvm  # noqa: E402
from src.mercado.providers.b3_cotahist import iterar_cotacoes  # noqa: E402
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
    sha256_fca,
    ticker_formato_elegivel,
)


ANO = 2025
REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
TIPO_MERCADO_VISTA = "010"


def _somente_digitos(valor: object) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def _catalogo_sistema() -> dict[str, dict[str, str]]:
    if not BANCO_DUCKDB.is_file():
        raise FileNotFoundError(BANCO_DUCKDB)

    con = conectar_cvm(read_only=True)
    try:
        linhas = con.execute(
            """
            SELECT CD_CVM, CNPJ_CIA, DENOM_CIA
            FROM empresas
            ORDER BY CD_CVM
            """
        ).fetchall()
    finally:
        con.close()

    saida = {}
    for cd_cvm, cnpj, nome in linhas:
        cd = str(cd_cvm).strip().zfill(6)
        saida[cd] = {
            "cnpj": _somente_digitos(cnpj).zfill(14),
            "nome": str(nome or "").strip(),
        }
    return saida


def _escrever_csv(caminho: Path, linhas: list[dict], campos: list[str]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=campos,
            delimiter=";",
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def executar(cotahist_2025: Path) -> None:
    if not cotahist_2025.is_file():
        raise FileNotFoundError(cotahist_2025)

    print("=" * 78)
    print("SISTEMA CVM — D.4 — DIAGNÓSTICO CATÁLOGO FCA 2025")
    print("=" * 78)

    print("Baixando/reutilizando FCA 2025 da CVM...")
    fca_zip = baixar_fca(ANO)
    print(f"FCA: {fca_zip}")
    print(f"FCA SHA-256: {sha256_fca(fca_zip)}")

    sistema = _catalogo_sistema()
    registros_fca, ambiguidades_cnpj = ler_fca_valores_mobiliarios(
        fca_zip,
        ano=ANO,
    )

    candidatos = [
        registro
        for registro in registros_fca
        if ticker_formato_elegivel(registro.codigo_negociacao)
    ]

    donos_ticker: dict[str, set[str]] = defaultdict(set)
    for registro in candidatos:
        if registro.cd_cvm:
            donos_ticker[registro.codigo_negociacao].add(registro.cd_cvm)

    tickers_ambiguos = {
        ticker: codigos
        for ticker, codigos in donos_ticker.items()
        if len(codigos) > 1
    }

    tickers_candidatos = {
        registro.codigo_negociacao for registro in candidatos
    }

    cotahist: dict[str, dict[str, object]] = {}
    for cotacao in iterar_cotacoes(cotahist_2025):
        if (
            cotacao.tipo_mercado != TIPO_MERCADO_VISTA
            or cotacao.ticker not in tickers_candidatos
        ):
            continue

        item = cotahist.setdefault(
            cotacao.ticker,
            {
                "datas": set(),
                "isins": set(),
                "especificacoes": set(),
            },
        )
        item["datas"].add(cotacao.data)
        if cotacao.isin:
            item["isins"].add(cotacao.isin)
        if cotacao.especificacao:
            item["especificacoes"].add(cotacao.especificacao)

    relatorio: list[dict] = []
    validados_por_cd: dict[str, set[str]] = defaultdict(set)

    for registro in sorted(
        registros_fca,
        key=lambda x: (
            x.cd_cvm or "",
            x.codigo_negociacao,
            x.data_inicio_negociacao or x.data_referencia or "",
        ),
    ):
        ticker = registro.codigo_negociacao
        formato_valido = ticker_formato_elegivel(ticker)
        no_sistema = bool(registro.cd_cvm and registro.cd_cvm in sistema)

        cnpj_sistema = (
            sistema.get(registro.cd_cvm, {}).get("cnpj", "")
            if registro.cd_cvm
            else ""
        )
        cnpj_confere = bool(
            no_sistema
            and cnpj_sistema
            and registro.cnpj
            and cnpj_sistema == registro.cnpj
        )

        dados_cotahist = cotahist.get(ticker)
        datas = (
            sorted(dados_cotahist["datas"])
            if dados_cotahist
            else []
        )
        isins = (
            sorted(dados_cotahist["isins"])
            if dados_cotahist
            else []
        )
        especificacoes = (
            sorted(dados_cotahist["especificacoes"])
            if dados_cotahist
            else []
        )

        if not registro.cd_cvm:
            status = "CD_CVM_NAO_RESOLVIDO"
        elif not formato_valido:
            status = "CODIGO_NEGOCIACAO_FORA_ESCOPO"
        elif ticker in tickers_ambiguos:
            status = "TICKER_REIVINDICADO_POR_MULTIPLOS_CD_CVM"
        elif no_sistema and not cnpj_confere:
            status = "CNPJ_DIVERGENTE_DO_CATALOGO_SISTEMA"
        elif datas and no_sistema:
            status = "VALIDADO_COTAHIST_2025"
            validados_por_cd[registro.cd_cvm].add(ticker)
        elif datas:
            status = "NEGOCIOU_2025_FORA_UNIVERSO_SISTEMA"
        elif (
            registro.data_fim_negociacao is not None
            and registro.data_fim_negociacao.year < ANO
        ):
            status = "HISTORICO_FCA_SEM_NEGOCIACAO_2025"
        elif no_sistema:
            status = "FCA_SEM_NEGOCIACAO_COTAHIST_2025"
        else:
            status = "FORA_UNIVERSO_SISTEMA"

        relatorio.append(
            {
                "CD_CVM": registro.cd_cvm or "",
                "CNPJ": registro.cnpj,
                "DENOM_SISTEMA": sistema.get(
                    registro.cd_cvm or "",
                    {},
                ).get("nome", ""),
                "NOME_FCA": registro.nome_empresarial,
                "TICKER": ticker,
                "VALOR_MOBILIARIO": registro.valor_mobiliario,
                "SIGLA_CLASSE_PREF": registro.sigla_classe_preferencial,
                "CLASSE_PREF": registro.classe_preferencial,
                "COMPOSICAO_BDR_UNIT": registro.composicao_bdr_unit,
                "MERCADO_FCA": registro.mercado,
                "ENTIDADE": registro.sigla_entidade_administradora,
                "DT_INICIO_NEGOCIACAO": (
                    registro.data_inicio_negociacao.isoformat()
                    if registro.data_inicio_negociacao
                    else ""
                ),
                "DT_FIM_NEGOCIACAO": (
                    registro.data_fim_negociacao.isoformat()
                    if registro.data_fim_negociacao
                    else ""
                ),
                "SEGMENTO": registro.segmento,
                "FORMATO_TICKER_ELEGIVEL": formato_valido,
                "NO_CATALOGO_SISTEMA": no_sistema,
                "CNPJ_CONFERE": cnpj_confere,
                "NEGOCIOU_2025": bool(datas),
                "PRIMEIRA_DATA_2025": (
                    datas[0].isoformat() if datas else ""
                ),
                "ULTIMA_DATA_2025": (
                    datas[-1].isoformat() if datas else ""
                ),
                "PREGOES_2025": len(datas),
                "ISINS_2025": "|".join(isins),
                "ESPECIFICACOES_2025": "|".join(especificacoes),
                "STATUS": status,
            }
        )

    empresas_com_ticker = set(validados_por_cd)
    sem_ticker = []

    for cd_cvm, dados in sorted(sistema.items()):
        if cd_cvm in empresas_com_ticker:
            continue
        sem_ticker.append(
            {
                "CD_CVM": cd_cvm,
                "CNPJ": dados["cnpj"],
                "DENOM_CIA": dados["nome"],
            }
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = REPORTS_DIR / "catalogo_fca_2025_diagnostico.csv"
    caminho_sem_ticker = REPORTS_DIR / "catalogo_fca_2025_sem_ticker.csv"

    campos = list(relatorio[0].keys()) if relatorio else []
    if campos:
        _escrever_csv(caminho_relatorio, relatorio, campos)
    _escrever_csv(
        caminho_sem_ticker,
        sem_ticker,
        ["CD_CVM", "CNPJ", "DENOM_CIA"],
    )

    linhas_validas = [
        r for r in relatorio
        if r["STATUS"] == "VALIDADO_COTAHIST_2025"
    ]
    tickers_validados = {r["TICKER"] for r in linhas_validas}

    print()
    print("RESUMO")
    print("-" * 78)
    print(f"Empresas no Sistema CVM: {len(sistema):,}")
    print(f"Registros semânticos FCA: {len(registros_fca):,}")
    print(f"Candidatos ação/unit por formato: {len(candidatos):,}")
    print(f"Tickers candidatos únicos: {len(tickers_candidatos):,}")
    print(f"Tickers validados no COTAHIST 2025: {len(tickers_validados):,}")
    print(
        "Empresas do sistema com >=1 ticker validado: "
        f"{len(empresas_com_ticker):,}"
    )
    print(
        "Empresas do sistema sem ticker validado em 2025: "
        f"{len(sem_ticker):,}"
    )
    print(f"CNPJ ambíguos no FCA: {len(ambiguidades_cnpj):,}")
    print(f"Tickers ambíguos entre CD_CVM: {len(tickers_ambiguos):,}")
    print()

    status_contagem: dict[str, int] = defaultdict(int)
    for linha in relatorio:
        status_contagem[linha["STATUS"]] += 1

    print("STATUS")
    print("-" * 78)
    for status, quantidade in sorted(status_contagem.items()):
        print(f"{status:44s} | {quantidade:5d}")

    if ambiguidades_cnpj:
        print()
        print("CNPJ AMBÍGUOS — BLOQUEANTES PARA AUTOMAÇÃO")
        print("-" * 78)
        for cnpj, codigos in sorted(ambiguidades_cnpj.items())[:20]:
            print(f"{cnpj} | {sorted(codigos)}")

    if tickers_ambiguos:
        print()
        print("TICKERS AMBÍGUOS — BLOQUEANTES PARA AUTOMAÇÃO")
        print("-" * 78)
        for ticker, codigos in sorted(tickers_ambiguos.items())[:20]:
            print(f"{ticker} | {sorted(codigos)}")

    print()
    print(f"Relatório detalhado: {caminho_relatorio}")
    print(f"Empresas sem ticker: {caminho_sem_ticker}")
    print()
    print("RESULTADO: DIAGNÓSTICO CONCLUÍDO")
    print(
        "Nenhum novo INSTRUMENTO_ID foi criado e nenhum catálogo oficial "
        "foi alterado."
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python tests/mercado/diagnostico_catalogo_fca_2025.py "
            "<COTAHIST_A2025.ZIP>"
        )

    executar(Path(sys.argv[1]))


if __name__ == "__main__":
    main()

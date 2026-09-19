from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.diagnostico_historico import (  # noqa: E402
    diagnosticar_ano,
    escrever_diagnostico,
)
from src.mercado.reconciliacao_historica import (  # noqa: E402
    ler_csv_semicolon,
    reconciliar_diagnostico,
    serializar_resultados,
    escrever_csv_semicolon,
)
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
)


ANOS = tuple(range(2010, 2024))
ANOS_FCA = tuple(range(2010, 2025))

REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
RAW_COTAHIST = ROOT_DIR / "data" / "market" / "raw" / "b3" / "cotahist"
REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
EXCECOES = REFERENCE_DIR / "vinculos_validados_2025.csv"

SAIDA_GLOBAL = REPORT_ROOT / "inventario_global_2010_2023.csv"
SAIDA_NOVOS = REPORT_ROOT / "candidatos_instrumentos_historicos_2010_2023.csv"
SAIDA_ALIASES = REPORT_ROOT / "aliases_historicos_2010_2023.csv"
SAIDA_PENDENCIAS = REPORT_ROOT / "pendencias_historicas_2010_2023.csv"


def _ler_csv(caminho: Path, *, delimiter: str = ",") -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=delimiter))


def _catalogo_sistema() -> set[str]:
    con = conectar_cvm(read_only=True)
    try:
        return {
            str(x[0]).strip().zfill(6)
            for x in con.execute("SELECT CD_CVM FROM empresas").fetchall()
        }
    finally:
        con.close()


def _agregar_grupos_novos(
    linhas: list[dict[str, str]],
) -> list[dict[str, str]]:
    grupos: dict[str, dict[str, object]] = {}

    for linha in linhas:
        if linha["STATUS"] != "NOVO_INSTRUMENTO_HISTORICO_CANDIDATO":
            continue

        chave = linha["CHAVE_INSTRUMENTO"]
        grupo = grupos.setdefault(
            chave,
            {
                "CHAVE_INSTRUMENTO": chave,
                "CD_CVM": linha["CD_CVM"],
                "TIPO_ATIVO": linha["TIPO_ATIVO"],
                "CLASSE": linha["CLASSE"],
                "tickers": set(),
                "anos": set(),
                "primeira": linha["PRIMEIRA_DATA"],
                "ultima": linha["ULTIMA_DATA"],
                "fontes": set(),
            },
        )
        grupo["tickers"].add(linha["TICKER"])
        grupo["anos"].add(int(linha["ANO"]))
        grupo["primeira"] = min(grupo["primeira"], linha["PRIMEIRA_DATA"])
        grupo["ultima"] = max(grupo["ultima"], linha["ULTIMA_DATA"])
        if linha["FONTE"]:
            grupo["fontes"].add(linha["FONTE"])

    saida = []
    for chave, g in sorted(grupos.items()):
        saida.append(
            {
                "CHAVE_INSTRUMENTO": chave,
                "CD_CVM": g["CD_CVM"],
                "TIPO_ATIVO": g["TIPO_ATIVO"],
                "CLASSE": g["CLASSE"],
                "TICKERS": "|".join(sorted(g["tickers"])),
                "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
                "PRIMEIRA_DATA_OBSERVADA": g["primeira"],
                "ULTIMA_DATA_OBSERVADA": g["ultima"],
                "FONTES": "|".join(sorted(g["fontes"])),
                "STATUS": "CANDIDATO_GLOBAL_SEM_ID",
            }
        )
    return saida


def _agregar_aliases(
    linhas: list[dict[str, str]],
) -> list[dict[str, str]]:
    grupos: dict[tuple[str, str], dict[str, object]] = {}

    for linha in linhas:
        if linha["STATUS"] != "ALIAS_EXISTENTE_FORTE":
            continue

        chave = (linha["INSTRUMENTO_ID"], linha["TICKER"])
        grupo = grupos.setdefault(
            chave,
            {
                "INSTRUMENTO_ID": linha["INSTRUMENTO_ID"],
                "TICKER": linha["TICKER"],
                "CD_CVM": linha["CD_CVM"],
                "TIPO_ATIVO": linha["TIPO_ATIVO"],
                "CLASSE": linha["CLASSE"],
                "anos": set(),
                "primeira": linha["PRIMEIRA_DATA"],
                "ultima": linha["ULTIMA_DATA"],
                "fontes": set(),
            },
        )
        grupo["anos"].add(int(linha["ANO"]))
        grupo["primeira"] = min(grupo["primeira"], linha["PRIMEIRA_DATA"])
        grupo["ultima"] = max(grupo["ultima"], linha["ULTIMA_DATA"])
        if linha["FONTE"]:
            grupo["fontes"].add(linha["FONTE"])

    saida = []
    for _, g in sorted(grupos.items()):
        saida.append(
            {
                "INSTRUMENTO_ID": g["INSTRUMENTO_ID"],
                "TICKER": g["TICKER"],
                "CD_CVM": g["CD_CVM"],
                "TIPO_ATIVO": g["TIPO_ATIVO"],
                "CLASSE": g["CLASSE"],
                "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
                "PRIMEIRA_DATA_OBSERVADA": g["primeira"],
                "ULTIMA_DATA_OBSERVADA": g["ultima"],
                "FONTES": "|".join(sorted(g["fontes"])),
                "STATUS": "ALIAS_GLOBAL_CANDIDATO",
            }
        )
    return saida


def _agregar_pendencias(
    linhas: list[dict[str, str]],
) -> list[dict[str, str]]:
    grupos: dict[tuple[str, str], dict[str, object]] = {}

    for linha in linhas:
        if not (
            linha["STATUS"].startswith("REVISAO_")
            or linha["STATUS"] == "SEM_EVIDENCIA_SUFICIENTE"
        ):
            continue

        chave = (linha["TICKER"], linha["STATUS"])
        grupo = grupos.setdefault(
            chave,
            {
                "TICKER": linha["TICKER"],
                "STATUS": linha["STATUS"],
                "anos": set(),
                "cds": set(),
                "detalhes": set(),
            },
        )
        grupo["anos"].add(int(linha["ANO"]))
        if linha["CD_CVM"]:
            grupo["cds"].add(linha["CD_CVM"])
        if linha["DETALHE"]:
            grupo["detalhes"].add(linha["DETALHE"])

    return [
        {
            "TICKER": g["TICKER"],
            "STATUS": g["STATUS"],
            "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
            "CD_CVM": "|".join(sorted(g["cds"])),
            "DETALHES": " || ".join(sorted(g["detalhes"])),
        }
        for _, g in sorted(grupos.items())
    ]


def main() -> None:
    print("=" * 108)
    print("SISTEMA CVM — D.5 — INVENTÁRIO HISTÓRICO GLOBAL 2010–2023")
    print("=" * 108)
    print(
        "Modo: somente leitura. Nenhum INSTRUMENTO_ID será alocado e nenhum "
        "catálogo/banco será alterado."
    )

    instrumentos = _ler_csv(REFERENCE_DIR / "instrumentos.csv")
    excecoes = ler_csv_semicolon(EXCECOES)
    sistema = _catalogo_sistema()

    print()
    print("Carregando FCA 2010–2024 (cache local será reutilizado)...")
    fca_por_ano = {}
    for ano in ANOS_FCA:
        caminho = baixar_fca(ano)
        registros, ambiguos = ler_fca_valores_mobiliarios(
            caminho,
            ano=ano,
        )
        fca_por_ano[ano] = registros
        print(
            f"FCA {ano}: {len(registros):>5,} registros | "
            f"CNPJ ambíguos: {len(ambiguos)}"
        )

    global_linhas: list[dict[str, str]] = []

    for ano in reversed(ANOS):
        print()
        print("-" * 108)
        print(f"ANO {ano}")
        print("-" * 108)

        cotahist = (
            RAW_COTAHIST
            / str(ano)
            / f"COTAHIST_A{ano}.ZIP"
        )
        if not cotahist.is_file():
            raise FileNotFoundError(cotahist)

        report_dir = REPORT_ROOT / str(ano)
        diag_path = report_dir / f"diagnostico_identidade_{ano}.csv"
        rec_path = report_dir / f"reconciliacao_identidade_{ano}.csv"

        diagnostico = diagnosticar_ano(
            caminho_cotahist=cotahist,
            ano=ano,
            reference_dir=REFERENCE_DIR,
            registros_fca=fca_por_ano[ano],
            cd_cvm_sistema=sistema,
        )
        escrever_diagnostico(diag_path, diagnostico)

        janela = {
            x: fca_por_ano[x]
            for x in (ano - 1, ano, ano + 1)
            if x in fca_por_ano
        }
        reconciliados = reconciliar_diagnostico(
            diagnostico=diagnostico,
            instrumentos=instrumentos,
            registros_fca_por_ano=janela,
            cd_cvm_sistema=sistema,
            excecoes_validadas=excecoes,
        )
        serializados = serializar_resultados(reconciliados)

        diag_por_ticker = {
            x["TICKER"]: x
            for x in diagnostico
        }
        linhas_ano = []
        for linha in serializados:
            diag = diag_por_ticker[linha["TICKER"]]
            item = {
                "ANO": str(ano),
                "PRIMEIRA_DATA": diag["PRIMEIRA_DATA"],
                "ULTIMA_DATA": diag["ULTIMA_DATA"],
                **linha,
            }
            linhas_ano.append(item)
            global_linhas.append(item)

        escrever_csv_semicolon(rec_path, linhas_ano)

        c = Counter(x["STATUS"] for x in linhas_ano)
        print(
            f"Tickers: {len(linhas_ano):,} | "
            f"resolvidos={c['RESOLVIDO_EXISTENTE']:,} | "
            f"aliases={c['ALIAS_EXISTENTE_FORTE']:,} | "
            f"novos={c['NOVO_INSTRUMENTO_HISTORICO_CANDIDATO']:,} | "
            f"fora={c['FORA_UNIVERSO_SISTEMA']:,} | "
            f"sem_evidência={c['SEM_EVIDENCIA_SUFICIENTE']:,}"
        )

    escrever_csv_semicolon(SAIDA_GLOBAL, global_linhas)

    novos = _agregar_grupos_novos(global_linhas)
    aliases = _agregar_aliases(global_linhas)
    pendencias = _agregar_pendencias(global_linhas)

    escrever_csv_semicolon(SAIDA_NOVOS, novos)
    escrever_csv_semicolon(SAIDA_ALIASES, aliases)
    escrever_csv_semicolon(SAIDA_PENDENCIAS, pendencias)

    contagem = Counter(x["STATUS"] for x in global_linhas)
    revisoes = sum(
        qtd
        for status, qtd in contagem.items()
        if status.startswith("REVISAO_")
    )

    print()
    print("=" * 108)
    print("RESUMO GLOBAL 2010–2023")
    print("=" * 108)
    print(f"Observações ticker-ano: {len(global_linhas):,}")
    print(f"Tickers únicos observados: {len({x['TICKER'] for x in global_linhas}):,}")
    print(f"Já resolvidos pelo catálogo: {contagem['RESOLVIDO_EXISTENTE']:,}")
    print(f"Alias ticker-ano com evidência forte: {contagem['ALIAS_EXISTENTE_FORTE']:,}")
    print(f"Aliases históricos únicos candidatos: {len(aliases):,}")
    print(
        "Ocorrências de novos instrumentos históricos: "
        f"{contagem['NOVO_INSTRUMENTO_HISTORICO_CANDIDATO']:,}"
    )
    print(f"Grupos históricos novos únicos: {len(novos):,}")
    print(f"Fora do universo contábil: {contagem['FORA_UNIVERSO_SISTEMA']:,}")
    print(f"Revisões necessárias: {revisoes:,}")
    print(
        "Sem evidência suficiente: "
        f"{contagem['SEM_EVIDENCIA_SUFICIENTE']:,}"
    )
    print(f"Pendências únicas: {len(pendencias):,}")

    print()
    print("ARQUIVOS GLOBAIS")
    print("-" * 108)
    print(SAIDA_GLOBAL)
    print(SAIDA_NOVOS)
    print(SAIDA_ALIASES)
    print(SAIDA_PENDENCIAS)

    if pendencias:
        print()
        print("PENDÊNCIAS ÚNICAS")
        print("-" * 108)
        for item in pendencias:
            print(
                f"{item['TICKER']:<12} | {item['STATUS']:<38} | "
                f"anos={item['ANOS']:<35} | {item['CD_CVM']}"
            )

    print()
    print("RESULTADO: INVENTÁRIO GLOBAL GERADO")
    print(
        "Não promover nem alocar IDs ainda. O próximo gate será construído "
        "sobre os grupos globais e as pendências resultantes."
    )


if __name__ == "__main__":
    main()

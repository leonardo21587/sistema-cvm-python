from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.reconciliacao_historica import (  # noqa: E402
    ler_csv_semicolon,
    escrever_csv_semicolon,
)
from src.mercado.reconciliacao_nome_historica import (  # noqa: E402
    extrair_nomes_ticker_ano,
    reconciliar_por_nome_b3,
)


REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
RAW_ROOT = ROOT_DIR / "data" / "market" / "raw" / "b3" / "cotahist"
REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"

ENTRADA = REPORT_ROOT / "inventario_global_2010_2023.csv"
SAIDA = REPORT_ROOT / "inventario_global_2010_2023_nome_b3.csv"
CONFLITOS = REPORT_ROOT / "conflitos_nome_b3_2010_2023.csv"
REVISOES = REPORT_ROOT / "revisoes_nome_b3_2010_2023.csv"
PENDENCIAS = REPORT_ROOT / "pendencias_pos_nome_b3_2010_2023.csv"


def _ler_instrumentos() -> list[dict[str, str]]:
    with (REFERENCE_DIR / "instrumentos.csv").open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        return list(csv.DictReader(arquivo))


def _mapas_instrumentos(
    instrumentos: list[dict[str, str]],
) -> tuple[
    dict[str, str],
    dict[tuple[str, str, str], set[str]],
]:
    por_id = {}
    por_chave: dict[tuple[str, str, str], set[str]] = {}

    for linha in instrumentos:
        instrumento_id = linha["INSTRUMENTO_ID"].strip()
        cd = linha["CD_CVM"].strip().zfill(6)
        tipo = linha["TIPO_ATIVO"].strip().upper()
        classe = linha["CLASSE"].strip().upper()

        por_id[instrumento_id] = cd
        por_chave.setdefault(
            (cd, tipo, classe),
            set(),
        ).add(instrumento_id)

    return por_id, por_chave


def _pendencias(linhas: list[dict[str, str]]) -> list[dict[str, str]]:
    grupos: dict[str, set[int]] = {}
    for linha in linhas:
        if linha["STATUS"] != "SEM_EVIDENCIA_SUFICIENTE":
            continue
        grupos.setdefault(linha["TICKER"], set()).add(int(linha["ANO"]))

    return [
        {
            "TICKER": ticker,
            "ANOS": "|".join(str(x) for x in sorted(anos)),
            "STATUS": "SEM_EVIDENCIA_SUFICIENTE",
        }
        for ticker, anos in sorted(grupos.items())
    ]


def main() -> None:
    if not ENTRADA.is_file():
        raise FileNotFoundError(ENTRADA)

    print("=" * 108)
    print("SISTEMA CVM — D.5 — RECONCILIAÇÃO POR NOME_RESUMIDO B3 2010–2023")
    print("=" * 108)
    print(
        "Esta etapa fará uma varredura leve dos COTAHIST apenas para "
        "NOME_RESUMIDO. Nenhum catálogo/banco será alterado."
    )

    inventario = ler_csv_semicolon(ENTRADA)
    instrumentos = _ler_instrumentos()
    instrumento_para_cd, instrumentos_por_chave = _mapas_instrumentos(
        instrumentos
    )

    tickers_por_ano: dict[int, set[str]] = {}
    for linha in inventario:
        ano = int(linha["ANO"])
        tickers_por_ano.setdefault(ano, set()).add(
            linha["TICKER"].strip().upper()
        )

    caminhos = {
        ano: RAW_ROOT / str(ano) / f"COTAHIST_A{ano}.ZIP"
        for ano in range(2010, 2024)
    }
    faltantes = [ano for ano, p in caminhos.items() if not p.is_file()]
    if faltantes:
        raise FileNotFoundError(
            "COTAHIST ausente para: "
            + ", ".join(str(x) for x in faltantes)
        )

    print()
    print("Extraindo NOME_RESUMIDO dos 14 COTAHISTs...")
    nomes = extrair_nomes_ticker_ano(
        caminhos_por_ano=caminhos,
        tickers_por_ano=tickers_por_ano,
    )
    print(f"Combinações ticker-ano com nome B3: {len(nomes):,}")

    antes = Counter(x["STATUS"] for x in inventario)

    saida, conflitos, revisoes = reconciliar_por_nome_b3(
        inventario=inventario,
        nomes_por_ticker_ano=nomes,
        instrumento_para_cd=instrumento_para_cd,
        instrumentos_por_chave=instrumentos_por_chave,
    )

    depois = Counter(x["STATUS"] for x in saida)
    pendencias = _pendencias(saida)

    escrever_csv_semicolon(SAIDA, saida)
    escrever_csv_semicolon(CONFLITOS, conflitos)
    escrever_csv_semicolon(REVISOES, revisoes)
    escrever_csv_semicolon(PENDENCIAS, pendencias)

    resolvidos = (
        depois["ALIAS_EXISTENTE_NOME_B3"]
        + depois["NOVO_INSTRUMENTO_HISTORICO_NOME_B3"]
        + depois["FORA_UNIVERSO_NOME_B3"]
    )

    print()
    print("RESUMO")
    print("-" * 108)
    print(f"Sem evidência antes: {antes['SEM_EVIDENCIA_SUFICIENTE']:,}")
    print(
        "Aliases existentes resolvidos por nome: "
        f"{depois['ALIAS_EXISTENTE_NOME_B3']:,}"
    )
    print(
        "Instrumentos históricos resolvidos por nome: "
        f"{depois['NOVO_INSTRUMENTO_HISTORICO_NOME_B3']:,}"
    )
    print(
        "Fora do universo resolvidos por nome: "
        f"{depois['FORA_UNIVERSO_NOME_B3']:,}"
    )
    print(f"Total resolvido nesta etapa: {resolvidos:,}")
    print(f"Sem evidência depois: {depois['SEM_EVIDENCIA_SUFICIENTE']:,}")
    print(
        "Redução percentual: "
        f"{(resolvidos / antes['SEM_EVIDENCIA_SUFICIENTE'] * 100 if antes['SEM_EVIDENCIA_SUFICIENTE'] else 0):.2f}%"
    )
    print(f"Nomes com múltiplas companhias ancoradas: {len(conflitos):,}")
    print(f"Linhas enviadas para revisão: {len(revisoes):,}")
    print(f"Pendências únicas restantes: {len(pendencias):,}")

    if conflitos:
        print()
        print("NOMES B3 AMBÍGUOS")
        print("-" * 108)
        for item in conflitos:
            print(
                f"{item['NOME_RESUMIDO']:<24} | "
                f"{item['COMPANHIAS']}"
            )

    if revisoes:
        print()
        print("REVISÕES")
        print("-" * 108)
        for item in revisoes:
            print(
                f"{item['ANO']} | {item['TICKER']:<12} | "
                f"{item['STATUS']:<34} | {item['CANDIDATOS']}"
            )

    if pendencias:
        print()
        print("PENDÊNCIAS ÚNICAS RESTANTES")
        print("-" * 108)
        for item in pendencias:
            print(f"{item['TICKER']:<12} | anos={item['ANOS']}")

    print()
    print("RESULTADO: RECONCILIAÇÃO POR NOME B3 GERADA")
    print("Não promover nem alocar IDs ainda.")


if __name__ == "__main__":
    main()

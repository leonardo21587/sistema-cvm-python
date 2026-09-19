from __future__ import annotations

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
from src.mercado.reconciliacao_isin_historica import (  # noqa: E402
    reconciliar_por_isin_global,
)


REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
ENTRADA = REPORT_ROOT / "inventario_global_2010_2023.csv"
SAIDA = REPORT_ROOT / "inventario_global_2010_2023_isin.csv"
CONFLITOS = REPORT_ROOT / "conflitos_isin_global_2010_2023.csv"
REVISOES = REPORT_ROOT / "revisoes_isin_global_2010_2023.csv"
PENDENCIAS = REPORT_ROOT / "pendencias_pos_isin_2010_2023.csv"


def _diagnosticos() -> list[dict[str, str]]:
    saida = []
    for ano in range(2010, 2024):
        caminho = (
            REPORT_ROOT
            / str(ano)
            / f"diagnostico_identidade_{ano}.csv"
        )
        if not caminho.is_file():
            raise FileNotFoundError(caminho)
        saida.extend(ler_csv_semicolon(caminho))
    return saida


def _pendencias(linhas: list[dict[str, str]]) -> list[dict[str, str]]:
    grupos: dict[str, dict[str, object]] = {}

    for linha in linhas:
        if linha["STATUS"] != "SEM_EVIDENCIA_SUFICIENTE":
            continue

        ticker = linha["TICKER"]
        g = grupos.setdefault(
            ticker,
            {"TICKER": ticker, "anos": set()},
        )
        g["anos"].add(int(linha["ANO"]))

    return [
        {
            "TICKER": g["TICKER"],
            "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
            "STATUS": "SEM_EVIDENCIA_SUFICIENTE",
        }
        for _, g in sorted(grupos.items())
    ]


def main() -> None:
    if not ENTRADA.is_file():
        raise FileNotFoundError(ENTRADA)

    print("=" * 108)
    print("SISTEMA CVM — D.5 — RECONCILIAÇÃO GLOBAL POR ISIN 2010–2023")
    print("=" * 108)
    print("Nenhum COTAHIST será relido. Nenhum catálogo/banco será alterado.")

    inventario = ler_csv_semicolon(ENTRADA)
    diagnosticos = _diagnosticos()

    antes = Counter(x["STATUS"] for x in inventario)

    saida, conflitos, revisoes = reconciliar_por_isin_global(
        inventario=inventario,
        diagnosticos=diagnosticos,
    )

    depois = Counter(x["STATUS"] for x in saida)
    pendencias = _pendencias(saida)

    escrever_csv_semicolon(SAIDA, saida)
    escrever_csv_semicolon(CONFLITOS, conflitos)
    escrever_csv_semicolon(REVISOES, revisoes)
    escrever_csv_semicolon(PENDENCIAS, pendencias)

    resolvidos = (
        depois["ALIAS_EXISTENTE_ISIN_GLOBAL"]
        + depois["NOVO_INSTRUMENTO_HISTORICO_ISIN_GLOBAL"]
        + depois["FORA_UNIVERSO_ISIN_GLOBAL"]
    )

    print()
    print("RESUMO")
    print("-" * 108)
    print(f"Observações ticker-ano: {len(inventario):,}")
    print(f"Sem evidência antes: {antes['SEM_EVIDENCIA_SUFICIENTE']:,}")
    print(
        "Aliases existentes resolvidos por ISIN: "
        f"{depois['ALIAS_EXISTENTE_ISIN_GLOBAL']:,}"
    )
    print(
        "Instrumentos históricos resolvidos por ISIN: "
        f"{depois['NOVO_INSTRUMENTO_HISTORICO_ISIN_GLOBAL']:,}"
    )
    print(
        "Fora do universo resolvidos por ISIN: "
        f"{depois['FORA_UNIVERSO_ISIN_GLOBAL']:,}"
    )
    print(f"Total resolvido nesta etapa: {resolvidos:,}")
    print(f"Sem evidência depois: {depois['SEM_EVIDENCIA_SUFICIENTE']:,}")
    print(
        "Redução percentual: "
        f"{(resolvidos / antes['SEM_EVIDENCIA_SUFICIENTE'] * 100 if antes['SEM_EVIDENCIA_SUFICIENTE'] else 0):.2f}%"
    )
    print(f"ISINs com âncoras conflitantes: {len(conflitos):,}")
    print(f"Linhas com múltiplos candidatos por ISIN: {len(revisoes):,}")
    print(f"Pendências únicas restantes: {len(pendencias):,}")

    if conflitos:
        print()
        print("ISINS COM ÂNCORAS CONFLITANTES")
        print("-" * 108)
        for item in conflitos:
            print(f"{item['ISIN']:<16} | {item['ANCORAS']}")

    if revisoes:
        print()
        print("REVISÕES POR ISIN")
        print("-" * 108)
        for item in revisoes:
            print(
                f"{item['ANO']} | {item['TICKER']:<12} | "
                f"{item['ISINS']} | {item['CANDIDATOS']}"
            )

    if pendencias:
        print()
        print("PENDÊNCIAS ÚNICAS RESTANTES")
        print("-" * 108)
        for item in pendencias:
            print(
                f"{item['TICKER']:<12} | anos={item['ANOS']}"
            )

    print()
    print(f"Inventário por ISIN: {SAIDA}")
    print(f"Conflitos: {CONFLITOS}")
    print(f"Revisões: {REVISOES}")
    print(f"Pendências: {PENDENCIAS}")
    print()
    print("RESULTADO: RECONCILIAÇÃO POR ISIN GERADA")
    print("Não promover nem alocar IDs ainda.")


if __name__ == "__main__":
    main()

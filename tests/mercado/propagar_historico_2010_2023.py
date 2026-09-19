from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.propagacao_historica import propagar_identidades  # noqa: E402
from src.mercado.reconciliacao_historica import (  # noqa: E402
    ler_csv_semicolon,
    escrever_csv_semicolon,
)


REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
ENTRADA = REPORT_ROOT / "inventario_global_2010_2023.csv"
SAIDA = REPORT_ROOT / "inventario_global_2010_2023_propagado.csv"
REVISOES = REPORT_ROOT / "revisoes_propagacao_2010_2023.csv"
PENDENCIAS = REPORT_ROOT / "pendencias_pos_propagacao_2010_2023.csv"


def _pendencias_unicas(
    linhas: list[dict[str, str]],
) -> list[dict[str, str]]:
    grupos: dict[tuple[str, str], dict[str, object]] = {}

    for linha in linhas:
        status = linha["STATUS"]
        if not (
            status == "SEM_EVIDENCIA_SUFICIENTE"
            or status.startswith("REVISAO_")
        ):
            continue

        chave = (linha["TICKER"], status)
        g = grupos.setdefault(
            chave,
            {
                "TICKER": linha["TICKER"],
                "STATUS": status,
                "anos": set(),
                "cds": set(),
            },
        )
        g["anos"].add(int(linha["ANO"]))
        if linha.get("CD_CVM", ""):
            g["cds"].add(linha["CD_CVM"])

    return [
        {
            "TICKER": g["TICKER"],
            "STATUS": g["STATUS"],
            "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
            "CD_CVM": "|".join(sorted(g["cds"])),
        }
        for _, g in sorted(grupos.items())
    ]


def main() -> None:
    if not ENTRADA.is_file():
        raise FileNotFoundError(ENTRADA)

    print("=" * 108)
    print("SISTEMA CVM — D.5 — PROPAGAÇÃO TEMPORAL CONSERVADORA 2010–2023")
    print("=" * 108)
    print("Nenhum COTAHIST será relido. Nenhum catálogo/banco será alterado.")

    linhas = ler_csv_semicolon(ENTRADA)
    antes = Counter(x["STATUS"] for x in linhas)

    propagado, revisoes = propagar_identidades(linhas)
    depois = Counter(x["STATUS"] for x in propagado)
    pendencias = _pendencias_unicas(propagado)

    escrever_csv_semicolon(SAIDA, propagado)
    escrever_csv_semicolon(REVISOES, revisoes)
    escrever_csv_semicolon(PENDENCIAS, pendencias)

    existentes = depois["ALIAS_EXISTENTE_PROPAGADO"]
    novos = depois["NOVO_INSTRUMENTO_HISTORICO_PROPAGADO"]
    fora = depois["FORA_UNIVERSO_PROPAGADO"]
    sem_antes = antes["SEM_EVIDENCIA_SUFICIENTE"]
    sem_depois = depois["SEM_EVIDENCIA_SUFICIENTE"]

    print()
    print("RESUMO")
    print("-" * 108)
    print(f"Observações ticker-ano: {len(linhas):,}")
    print(f"Sem evidência antes: {sem_antes:,}")
    print(f"Aliases existentes propagados: {existentes:,}")
    print(f"Instrumentos históricos propagados: {novos:,}")
    print(f"Fora do universo propagados: {fora:,}")
    print(f"Sem evidência depois: {sem_depois:,}")
    print(f"Redução absoluta: {sem_antes - sem_depois:,}")
    if sem_antes:
        reducao = (sem_antes - sem_depois) / sem_antes * 100
        print(f"Redução percentual: {reducao:.2f}%")
    print(f"Segmentos com âncoras conflitantes: {len(revisoes):,}")
    print(f"Pendências únicas restantes: {len(pendencias):,}")

    if revisoes:
        print()
        print("SEGMENTOS COM ÂNCORAS CONFLITANTES")
        print("-" * 108)
        for item in revisoes:
            print(
                f"{item['TICKER']:<12} | anos={item['ANOS']:<35} | "
                f"{item['TOKENS']}"
            )

    if pendencias:
        print()
        print("PENDÊNCIAS ÚNICAS RESTANTES")
        print("-" * 108)
        for item in pendencias:
            print(
                f"{item['TICKER']:<12} | {item['STATUS']:<38} | "
                f"anos={item['ANOS']:<35} | {item['CD_CVM']}"
            )

    print()
    print(f"Inventário propagado: {SAIDA}")
    print(f"Revisões de propagação: {REVISOES}")
    print(f"Pendências finais: {PENDENCIAS}")
    print()
    print("RESULTADO: PROPAGAÇÃO CANDIDATA GERADA")
    print("Não promover nem alocar IDs ainda.")


if __name__ == "__main__":
    main()

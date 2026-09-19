from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
)
from src.mercado.reconciliacao_historica import (  # noqa: E402
    ler_csv_semicolon,
    escrever_csv_semicolon,
)
from src.mercado.reconciliacao_nome_historica import (  # noqa: E402
    extrair_nomes_ticker_ano,
)
from src.mercado.reconciliacao_nome_fca_historica import (  # noqa: E402
    reconciliar_pendencias_por_nome_fca,
)


REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
RAW_ROOT = ROOT_DIR / "data" / "market" / "raw" / "b3" / "cotahist"
REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"

ENTRADA = REPORT_ROOT / "inventario_global_2010_2023_nome_b3.csv"
SAIDA = REPORT_ROOT / "inventario_global_2010_2023_nome_fca.csv"
CANDIDATOS = REPORT_ROOT / "candidatos_nome_fca_2010_2023.csv"
REVISOES = REPORT_ROOT / "revisoes_nome_fca_2010_2023.csv"
PENDENCIAS = REPORT_ROOT / "pendencias_pos_nome_fca_2010_2023.csv"


def _instrumentos() -> list[dict[str, str]]:
    with (REFERENCE_DIR / "instrumentos.csv").open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        return list(csv.DictReader(arquivo))


def _mapa_instrumentos(
    linhas: list[dict[str, str]],
) -> dict[tuple[str, str, str], set[str]]:
    saida: dict[tuple[str, str, str], set[str]] = {}
    for linha in linhas:
        chave = (
            linha["CD_CVM"].strip().zfill(6),
            linha["TIPO_ATIVO"].strip().upper(),
            linha["CLASSE"].strip().upper(),
        )
        saida.setdefault(chave, set()).add(
            linha["INSTRUMENTO_ID"].strip()
        )
    return saida


def _cds_sistema() -> set[str]:
    con = conectar_cvm(read_only=True)
    try:
        return {
            str(x[0]).strip().zfill(6)
            for x in con.execute("SELECT CD_CVM FROM empresas").fetchall()
        }
    finally:
        con.close()


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
        raise FileNotFoundError(
            f"Execute primeiro reconciliar_nome_b3_2010_2023.py: {ENTRADA}"
        )

    print("=" * 108)
    print("SISTEMA CVM — D.5 — PONTE NOME B3 -> NOME EMPRESARIAL FCA")
    print("=" * 108)
    print("Modo candidato. Nenhum catálogo/banco será alterado.")

    inventario = ler_csv_semicolon(ENTRADA)

    tickers_por_ano: dict[int, set[str]] = {}
    for linha in inventario:
        if linha["STATUS"] != "SEM_EVIDENCIA_SUFICIENTE":
            continue
        ano = int(linha["ANO"])
        tickers_por_ano.setdefault(ano, set()).add(
            linha["TICKER"].strip().upper()
        )

    caminhos = {
        ano: RAW_ROOT / str(ano) / f"COTAHIST_A{ano}.ZIP"
        for ano in range(2010, 2024)
    }

    print("Extraindo nomes B3 apenas das pendências...")
    nomes_b3 = extrair_nomes_ticker_ano(
        caminhos_por_ano=caminhos,
        tickers_por_ano=tickers_por_ano,
    )
    print(f"Combinações pendentes ticker-ano com nome: {len(nomes_b3):,}")

    print("Carregando FCA 2010–2024...")
    fca = []
    for ano in range(2010, 2025):
        caminho = baixar_fca(ano)
        registros, _ = ler_fca_valores_mobiliarios(
            caminho,
            ano=ano,
        )
        fca.extend(registros)

    antes = Counter(x["STATUS"] for x in inventario)

    saida, candidatos, revisoes = reconciliar_pendencias_por_nome_fca(
        inventario=inventario,
        nomes_b3=nomes_b3,
        registros_fca=fca,
        cd_cvm_sistema=_cds_sistema(),
        instrumentos_por_chave=_mapa_instrumentos(_instrumentos()),
    )

    depois = Counter(x["STATUS"] for x in saida)
    pendencias = _pendencias(saida)

    escrever_csv_semicolon(SAIDA, saida)
    escrever_csv_semicolon(CANDIDATOS, candidatos)
    escrever_csv_semicolon(REVISOES, revisoes)
    escrever_csv_semicolon(PENDENCIAS, pendencias)

    resolvidos = (
        depois["ALIAS_EXISTENTE_NOME_FCA"]
        + depois["NOVO_INSTRUMENTO_HISTORICO_NOME_FCA"]
        + depois["FORA_UNIVERSO_NOME_FCA"]
    )

    print()
    print("RESUMO")
    print("-" * 108)
    print(f"Sem evidência antes: {antes['SEM_EVIDENCIA_SUFICIENTE']:,}")
    print(
        "Aliases existentes resolvidos: "
        f"{depois['ALIAS_EXISTENTE_NOME_FCA']:,}"
    )
    print(
        "Instrumentos históricos candidatos resolvidos: "
        f"{depois['NOVO_INSTRUMENTO_HISTORICO_NOME_FCA']:,}"
    )
    print(
        "Fora do universo resolvidos: "
        f"{depois['FORA_UNIVERSO_NOME_FCA']:,}"
    )
    print(f"Total resolvido nesta etapa: {resolvidos:,}")
    print(f"Sem evidência depois: {depois['SEM_EVIDENCIA_SUFICIENTE']:,}")
    print(
        "Redução percentual: "
        f"{(resolvidos / antes['SEM_EVIDENCIA_SUFICIENTE'] * 100 if antes['SEM_EVIDENCIA_SUFICIENTE'] else 0):.2f}%"
    )
    print(f"Candidatos nome-FCA registrados: {len(candidatos):,}")
    print(f"Revisões necessárias: {len(revisoes):,}")
    print(f"Pendências únicas restantes: {len(pendencias):,}")

    if revisoes:
        print()
        print("REVISÕES")
        print("-" * 108)
        for item in revisoes:
            print(
                f"{item['TICKER']:<12} | "
                f"{item['STATUS']:<40} | "
                f"{item['CDS_CANDIDATOS']}"
            )

    if pendencias:
        print()
        print("PENDÊNCIAS ÚNICAS RESTANTES")
        print("-" * 108)
        for item in pendencias:
            print(f"{item['TICKER']:<12} | anos={item['ANOS']}")

    print()
    print(f"Candidatos detalhados: {CANDIDATOS}")
    print(f"Revisões: {REVISOES}")
    print(f"Pendências: {PENDENCIAS}")
    print("RESULTADO: PONTE NOME B3/FCA GERADA")
    print("Não promover nem alocar IDs ainda.")


if __name__ == "__main__":
    main()

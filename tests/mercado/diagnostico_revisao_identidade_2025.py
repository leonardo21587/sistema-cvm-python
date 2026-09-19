from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
DIAGNOSTICO = REPORTS_DIR / "catalogo_fca_2025_diagnostico.csv"
REVISAO = REPORTS_DIR / "catalogo_identidade_revisao_2025.csv"

TICKERS_ALVO = {
    "CALI11",
    "PETR4",
    "AZEV11",
    "IFCM11",
    "RAIZ4",
    "ELET3",
    "AXIA3",
    "NATU3",
    "NTCO3",
}


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)

    with caminho.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def _valor(linha: dict[str, str], campo: str) -> str:
    return str(linha.get(campo, "") or "").strip()


def main() -> None:
    print("=" * 90)
    print("SISTEMA CVM — D.4 — DIAGNÓSTICO DIRIGIDO DE IDENTIDADE")
    print("=" * 90)

    linhas = _ler_csv(DIAGNOSTICO)
    revisao = _ler_csv(REVISAO)

    print()
    print("CASOS EM REVISÃO")
    print("-" * 90)
    for linha in revisao:
        print(
            f"{_valor(linha, 'CD_CVM'):6s} | "
            f"{_valor(linha, 'TICKER'):8s} | "
            f"{_valor(linha, 'ISIN'):14s} | "
            f"{_valor(linha, 'PROBLEMAS')}"
        )

    print()
    print("LINHAS-FONTE DOS TICKERS-ALVO")
    print("-" * 90)

    alvo = [
        linha
        for linha in linhas
        if _valor(linha, "TICKER").upper() in TICKERS_ALVO
    ]

    alvo.sort(
        key=lambda x: (
            _valor(x, "CD_CVM"),
            _valor(x, "TICKER"),
            _valor(x, "DT_INICIO_NEGOCIACAO"),
            _valor(x, "DT_FIM_NEGOCIACAO"),
            _valor(x, "VALOR_MOBILIARIO"),
            _valor(x, "SIGLA_CLASSE_PREF"),
        )
    )

    for linha in alvo:
        print()
        print(
            f"{_valor(linha, 'CD_CVM')} | "
            f"{_valor(linha, 'TICKER')} | "
            f"status={_valor(linha, 'STATUS')}"
        )
        print(
            f"  CNPJ={_valor(linha, 'CNPJ')} | "
            f"nome={_valor(linha, 'NOME_FCA')}"
        )
        print(
            f"  valor_mobiliario={_valor(linha, 'VALOR_MOBILIARIO')!r}"
        )
        print(
            f"  sigla_classe_pref={_valor(linha, 'SIGLA_CLASSE_PREF')!r}"
        )
        print(
            f"  classe_pref={_valor(linha, 'CLASSE_PREF')!r}"
        )
        print(
            f"  composicao_unit={_valor(linha, 'COMPOSICAO_BDR_UNIT')!r}"
        )
        print(
            f"  mercado={_valor(linha, 'MERCADO_FCA')!r} | "
            f"entidade={_valor(linha, 'ENTIDADE')!r}"
        )
        print(
            f"  inicio_neg={_valor(linha, 'DT_INICIO_NEGOCIACAO')} | "
            f"fim_neg={_valor(linha, 'DT_FIM_NEGOCIACAO')}"
        )
        print(
            f"  inicio_2025={_valor(linha, 'PRIMEIRA_DATA_2025')} | "
            f"fim_2025={_valor(linha, 'ULTIMA_DATA_2025')} | "
            f"pregoes={_valor(linha, 'PREGOES_2025')}"
        )
        print(
            f"  ISIN={_valor(linha, 'ISINS_2025')!r}"
        )
        print(
            f"  especificacao_B3={_valor(linha, 'ESPECIFICACOES_2025')!r}"
        )

    print()
    print("AGRUPAMENTO POR CD_CVM — CONTINUIDADE POTENCIAL")
    print("-" * 90)

    por_cd: dict[str, list[dict[str, str]]] = defaultdict(list)
    for linha in alvo:
        if _valor(linha, "TICKER").upper() in {
            "ELET3",
            "AXIA3",
            "NATU3",
            "NTCO3",
        }:
            por_cd[_valor(linha, "CD_CVM")].append(linha)

    for cd_cvm, grupo in sorted(por_cd.items()):
        tickers = sorted({_valor(x, "TICKER") for x in grupo})
        print(f"CD_CVM {cd_cvm}: {tickers}")

        for ticker in tickers:
            linhas_ticker = [
                x for x in grupo if _valor(x, "TICKER") == ticker
            ]
            isins = sorted({
                _valor(x, "ISINS_2025")
                for x in linhas_ticker
                if _valor(x, "ISINS_2025")
            })
            especificacoes = sorted({
                _valor(x, "ESPECIFICACOES_2025")
                for x in linhas_ticker
                if _valor(x, "ESPECIFICACOES_2025")
            })
            primeira = sorted({
                _valor(x, "PRIMEIRA_DATA_2025")
                for x in linhas_ticker
                if _valor(x, "PRIMEIRA_DATA_2025")
            })
            ultima = sorted({
                _valor(x, "ULTIMA_DATA_2025")
                for x in linhas_ticker
                if _valor(x, "ULTIMA_DATA_2025")
            })

            print(
                f"  {ticker:6s} | ISIN={isins} | "
                f"B3={especificacoes} | "
                f"primeira={primeira} | ultima={ultima}"
            )

    print()
    print("RESULTADO: DIAGNÓSTICO CONCLUÍDO")
    print("Nenhum arquivo de referência ou banco foi alterado.")


if __name__ == "__main__":
    main()

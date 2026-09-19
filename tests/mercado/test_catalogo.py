from __future__ import annotations

import sys
from pathlib import Path

import duckdb


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.catalogo import (  # noqa: E402
    carregar_catalogo_referencia,
    tickers_catalogados,
)
from src.mercado.identidade import resolver_instrumento  # noqa: E402
from src.mercado.schema import criar_schema_mercado  # noqa: E402


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.3 — CATÁLOGO VERSIONADO")
    print("=" * 72)

    con = duckdb.connect(":memory:")
    try:
        criar_schema_mercado(con)
        resumo = carregar_catalogo_referencia(con)

        assert resumo == {
            "instrumentos": 8,
            "identificadores": 3,
            "tickers": 9,
        }

        assert resolver_instrumento(
            con,
            bolsa="B3",
            ticker="AXIA3",
            data_referencia="2025-11-10",
        ) == 3001

        assert resolver_instrumento(
            con,
            bolsa="B3",
            ticker="NATU3",
            data_referencia="2025-07-02",
        ) == 5003

        tickers = tickers_catalogados()
        assert {
            "PETR3",
            "PETR4",
            "TAEE11",
            "ELET3",
            "AXIA3",
            "MGLU3",
            "NATU3",
            "NTCO3",
        }.issubset(tickers)

    finally:
        con.close()

    print("RESULTADO: APROVADO")
    print("IDs estáveis versionados: aprovados")
    print("catálogo CSV -> DuckDB: aprovado")
    print("resolvedor temporal sobre catálogo: aprovado")


if __name__ == "__main__":
    main()

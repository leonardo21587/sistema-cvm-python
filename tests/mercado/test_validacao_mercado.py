from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import duckdb


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.schema import criar_schema_mercado  # noqa: E402
from src.mercado.validacao import detectar_descontinuidades  # noqa: E402


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.3 — DESCONTINUIDADES")
    print("=" * 72)

    con = duckdb.connect(":memory:")
    try:
        criar_schema_mercado(con)

        con.execute(
            """
            INSERT INTO instrumentos VALUES
            (1, '000001', 'ACAO', 'ON', 'BRL',
             DATE '2020-01-01', NULL, 'ATIVO', 'FIXTURE')
            """
        )
        con.execute(
            """
            INSERT INTO tickers_historico VALUES
            (1, 'B3', 'TEST3', DATE '2020-01-01',
             NULL, 'VIGENTE', 'FIXTURE')
            """
        )

        for data, fechamento in [
            ("2025-01-02", Decimal("10.00")),
            ("2025-01-03", Decimal("10.50")),
            ("2025-01-06", Decimal("20.00")),
        ]:
            con.execute(
                """
                INSERT INTO precos_diarios VALUES (
                    1, ?, 'TEST3',
                    ?, ?, ?, ?, ?,
                    1, 100, 1000.00,
                    'BRL', 'FIXTURE', 'fixture.txt',
                    TIMESTAMP '2026-09-19 08:00:00'
                )
                """,
                [
                    data,
                    fechamento,
                    fechamento,
                    fechamento,
                    fechamento,
                    fechamento,
                ],
            )

        alertas = detectar_descontinuidades(
            con,
            limiar_abs_log=0.35,
        )

        assert len(alertas) == 1
        assert alertas[0].data_atual.isoformat() == "2025-01-06"
        assert alertas[0].retorno_log > 0.35

    finally:
        con.close()

    print("RESULTADO: APROVADO")
    print("movimento normal: não sinalizado")
    print("descontinuidade extrema: sinalizada")
    print("detector: não bloqueante")


if __name__ == "__main__":
    main()

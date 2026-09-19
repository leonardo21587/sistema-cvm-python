from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.providers.cvm_fca import ticker_formato_elegivel  # noqa: E402


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.4 — REGRAS DE IDENTIDADE CANDIDATA")
    print("=" * 72)

    casos_validos = [
        "PETR3",
        "PETR4",
        "TAEE11",
        "B3SA3",
        "ELET3",
        "AXIA3",
    ]
    casos_fora = [
        "AMAR1",
        "AMAR2",
        "AMAR9",
        "PETR",
        "4030",
    ]

    assert all(ticker_formato_elegivel(x) for x in casos_validos)
    assert all(not ticker_formato_elegivel(x) for x in casos_fora)

    print("RESULTADO: APROVADO")
    print("ações ON/PN e units: elegíveis")
    print("direitos/recibos/códigos fora do padrão: fora do escopo")


if __name__ == "__main__":
    main()

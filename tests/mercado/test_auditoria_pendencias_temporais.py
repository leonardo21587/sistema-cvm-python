from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.mercado.auditar_pendencias_temporais_2010_2023 import _sobrepoe  # noqa: E402


def main() -> None:
    print("=" * 90)
    print("SISTEMA CVM — TESTE D.5 — AUDITORIA TEMPORAL")
    print("=" * 90)

    alvo_ini = date(2012, 1, 1)
    alvo_fim = date(2012, 12, 31)

    assert _sobrepoe(
        date(2010, 1, 1),
        date(2013, 1, 1),
        alvo_ini,
        alvo_fim,
    )
    assert not _sobrepoe(
        date(2014, 1, 1),
        None,
        alvo_ini,
        alvo_fim,
    )
    assert _sobrepoe(
        None,
        None,
        alvo_ini,
        alvo_fim,
    )

    print("RESULTADO: APROVADO")
    print("Sobreposição temporal FCA: aprovada")
    print("Intervalos abertos: preservados")


if __name__ == "__main__":
    main()

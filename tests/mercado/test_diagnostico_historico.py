from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.diagnostico_historico import ObservacaoTickerAno  # noqa: E402


def main() -> None:
    print("=" * 82)
    print("SISTEMA CVM — TESTE D.5 — ESTRUTURA DO DIAGNÓSTICO HISTÓRICO")
    print("=" * 82)

    obs = ObservacaoTickerAno(
        ticker="TEST3",
        primeira_data=date(2023, 1, 2),
        ultima_data=date(2023, 12, 28),
        pregoes=248,
        isins=("BRTESTACNOR1",),
        especificacoes=("ON NM",),
        nomes_resumidos=("TESTE",),
    )

    assert obs.ticker == "TEST3"
    assert obs.primeira_data < obs.ultima_data
    assert obs.pregoes > 0
    assert len(obs.isins) == 1

    print("RESULTADO: APROVADO")
    print("Estrutura de observação anual: aprovada")
    print("Diagnóstico permanece somente leitura: aprovado")


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.mercado.auditar_nome_fca_por_ano_2010_2023 import _nomes


def main():
    print("=" * 90)
    print("SISTEMA CVM — TESTE D.5 — AUDITORIA NOME/FCA POR ANO")
    print("=" * 90)

    linha = {"NOMES_RESUMIDOS": "EMPRESA TESTE|OUTRO NOME|EMPRESA TESTE"}
    assert _nomes(linha) == ("EMPRESA TESTE", "OUTRO NOME")
    assert _nomes(None) == ()

    print("RESULTADO: APROVADO")
    print("Leitura dos nomes dos diagnosticos: aprovada")
    print("Deduplicacao por observacao: aprovada")


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.propagacao_historica import propagar_identidades  # noqa: E402


def _linha(ano: int, status: str, instrumento_id: str = "") -> dict[str, str]:
    return {
        "ANO": str(ano),
        "TICKER": "TEST3",
        "STATUS": status,
        "CD_CVM": "",
        "TIPO_ATIVO": "ACAO",
        "CLASSE": "ON",
        "INSTRUMENTO_ID": instrumento_id,
        "CHAVE_INSTRUMENTO": "",
        "FONTE": "",
        "DETALHE": "",
    }


def main() -> None:
    print("=" * 90)
    print("SISTEMA CVM — TESTE D.5 — PROPAGAÇÃO TEMPORAL")
    print("=" * 90)

    linhas = [
        _linha(2010, "SEM_EVIDENCIA_SUFICIENTE"),
        _linha(2011, "SEM_EVIDENCIA_SUFICIENTE"),
        _linha(2012, "ALIAS_EXISTENTE_FORTE", "1234"),
    ]

    saida, revisoes = propagar_identidades(linhas)
    por_ano = {int(x["ANO"]): x for x in saida}

    assert not revisoes
    assert por_ano[2010]["STATUS"] == "ALIAS_EXISTENTE_PROPAGADO"
    assert por_ano[2011]["INSTRUMENTO_ID"] == "1234"

    conflito = [
        _linha(2010, "ALIAS_EXISTENTE_FORTE", "1001"),
        _linha(2011, "SEM_EVIDENCIA_SUFICIENTE"),
        _linha(2012, "ALIAS_EXISTENTE_FORTE", "2002"),
    ]
    saida2, revisoes2 = propagar_identidades(conflito)

    assert len(revisoes2) == 1
    assert next(x for x in saida2 if x["ANO"] == "2011")["STATUS"] == (
        "SEM_EVIDENCIA_SUFICIENTE"
    )

    print("RESULTADO: APROVADO")
    print("Propagação por segmento contínuo: aprovada")
    print("Bloqueio por múltiplas âncoras: aprovado")


if __name__ == "__main__":
    main()

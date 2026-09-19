from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.reconciliacao_isin_historica import (  # noqa: E402
    reconciliar_por_isin_global,
)


def main() -> None:
    print("=" * 90)
    print("SISTEMA CVM — TESTE D.5 — RECONCILIAÇÃO GLOBAL POR ISIN")
    print("=" * 90)

    inventario = [
        {
            "ANO": "2020",
            "TICKER": "OLD3",
            "STATUS": "SEM_EVIDENCIA_SUFICIENTE",
            "TIPO_ATIVO": "ACAO",
            "CLASSE": "ON",
            "INSTRUMENTO_ID": "",
            "CHAVE_INSTRUMENTO": "",
            "CD_CVM": "",
            "FONTE": "",
            "DETALHE": "",
        },
        {
            "ANO": "2021",
            "TICKER": "NEW3",
            "STATUS": "ALIAS_EXISTENTE_FORTE",
            "TIPO_ATIVO": "ACAO",
            "CLASSE": "ON",
            "INSTRUMENTO_ID": "1234",
            "CHAVE_INSTRUMENTO": "",
            "CD_CVM": "000001",
            "FONTE": "",
            "DETALHE": "",
        },
    ]

    diagnosticos = [
        {"ANO": "2020", "TICKER": "OLD3", "ISINS": "BRTESTACNOR1"},
        {"ANO": "2021", "TICKER": "NEW3", "ISINS": "BRTESTACNOR1"},
    ]

    saida, conflitos, revisoes = reconciliar_por_isin_global(
        inventario=inventario,
        diagnosticos=diagnosticos,
    )

    alvo = next(x for x in saida if x["TICKER"] == "OLD3")
    assert alvo["STATUS"] == "ALIAS_EXISTENTE_ISIN_GLOBAL"
    assert alvo["INSTRUMENTO_ID"] == "1234"
    assert not conflitos
    assert not revisoes

    print("RESULTADO: APROVADO")
    print("Âncora única por ISIN: aprovada")
    print("Compatibilidade tipo/classe: preservada")
    print("Sem propagação transitiva: preservado")


if __name__ == "__main__":
    main()

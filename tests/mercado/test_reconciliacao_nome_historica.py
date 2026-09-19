from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.reconciliacao_nome_historica import (  # noqa: E402
    normalizar_nome_b3,
    reconciliar_por_nome_b3,
)


def main() -> None:
    print("=" * 90)
    print("SISTEMA CVM — TESTE D.5 — NOME_RESUMIDO B3")
    print("=" * 90)

    assert normalizar_nome_b3("Companhia  S.A.") == "COMPANHIA S A"

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
            "CD_CVM": "",
            "FONTE": "",
            "DETALHE": "",
        },
        {
            "ANO": "2022",
            "TICKER": "NEW3",
            "STATUS": "ALIAS_EXISTENTE_FORTE",
            "TIPO_ATIVO": "ACAO",
            "CLASSE": "ON",
            "INSTRUMENTO_ID": "1234",
            "CHAVE_INSTRUMENTO": "",
            "CD_CVM": "",
            "FONTE": "",
            "DETALHE": "",
        },
    ]

    nomes = {
        (2020, "OLD3"): ("EMPRESA TESTE",),
        (2021, "NEW3"): ("EMPRESA TESTE",),
        (2022, "NEW3"): ("EMPRESA TESTE",),
    }

    saida, conflitos, revisoes = reconciliar_por_nome_b3(
        inventario=inventario,
        nomes_por_ticker_ano=nomes,
        instrumento_para_cd={"1234": "000001"},
        instrumentos_por_chave={
            ("000001", "ACAO", "ON"): {"1234"}
        },
    )

    alvo = next(x for x in saida if x["TICKER"] == "OLD3")
    assert alvo["STATUS"] == "ALIAS_EXISTENTE_NOME_B3"
    assert alvo["INSTRUMENTO_ID"] == "1234"
    assert not conflitos
    assert not revisoes

    print("RESULTADO: APROVADO")
    print("Nome exato normalizado: aprovado")
    print("Mínimo de duas evidências fortes: aprovado")
    print("Companhia única + tipo/classe: aprovado")


if __name__ == "__main__":
    main()

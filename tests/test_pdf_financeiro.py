from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from src.contexto_relatorio import (  # noqa: E402
    montar_contexto_relatorio,
)
from src.pdf_financeiro import (  # noqa: E402
    MIME_PDF,
    PeriodoInsuficientePDF,
    gerar_pdf_financeiro,
)


def _objetos_oficiais(layout: str, anos: list[int]) -> dict:
    base_oficial = pd.DataFrame(
        {
            "INDICADOR": ["ZERO", "AUSENTE", "NAO_APLICAVEL", "SINAL"],
            "VALOR": [0.0, "N/D", "N/A", -0.25],
        }
    )
    analise = base_oficial.copy(deep=True)
    vazio = pd.DataFrame()

    narrativa = None
    if len(anos) >= 2:
        narrativa = {
            "RESUMO_EXECUTIVO": (
                "A análise oficial preserva acentuação, "
                "sinais e limitações metodológicas."
            )
        }

    return {
        "identificacao": {
            "DENOM_CIA": "COMPANHIA DE TESTE S.A.",
            "CD_CVM": "001234",
            "CNPJ_CIA": "00.000.000/0001-00",
            "LAYOUT_CVM": layout,
            "FONTE": "DFP consolidadas / CVM",
            "DATA_GERACAO": "2026-09-18",
        },
        "anos": anos,
        "demonstracoes": {
            "BPA": vazio.copy(),
            "BPP": vazio.copy(),
            "DRE": vazio.copy(),
        },
        "indicadores": {
            "ANALISE": analise,
            "BASE_OFICIAL": base_oficial,
        },
        "narrativa": narrativa,
        "status_validacao": "OK",
        "validacao": pd.DataFrame(
            [{"TESTE": "Sentinelas", "STATUS": "OK"}]
        ),
        "metodologia": {"LAYOUT": layout},
        "fontes": pd.DataFrame([{"FONTE": "CVM"}]),
    }


def _contexto(layout: str, anos: list[int]) -> dict:
    return montar_contexto_relatorio(
        **_objetos_oficiais(layout, anos),
        modalidade="EXECUTIVO_ANALISTA",
    )


def testar_contexto_temporal_e_sentinelas() -> None:
    modos = {
        1: "PERIODO_INSUFICIENTE",
        2: "COMPARATIVO",
        3: "TRAJETORIA",
    }

    for layout in ("PADRAO", "FINANCEIRA"):
        for quantidade, modo in modos.items():
            anos = [2023, 2024, 2025][-quantidade:]
            objetos = _objetos_oficiais(layout, anos)
            original = deepcopy(objetos["indicadores"])
            contexto = montar_contexto_relatorio(
                **objetos,
                modalidade="EXECUTIVO_ANALISTA",
            )

            assert contexto["PERIODO"]["MODO_TEMPORAL"] == modo
            assert contexto["PERIODO"]["QTD_EXERCICIOS"] == quantidade

            valores = contexto["INDICADORES"]["BASE_OFICIAL"]["VALOR"].tolist()
            assert valores == [0.0, "N/D", "N/A", -0.25]
            assert objetos["indicadores"]["BASE_OFICIAL"].equals(
                original["BASE_OFICIAL"]
            )
            assert contexto["INDICADORES"]["BASE_OFICIAL"] is not (
                objetos["indicadores"]["BASE_OFICIAL"]
            )

    um_ano = _contexto("FINANCEIRA", [2025])
    assert um_ano["NARRATIVA"] is None

    try:
        gerar_pdf_financeiro(um_ano, "EXECUTIVO_ANALISTA")
    except PeriodoInsuficientePDF as erro:
        assert "pelo menos dois exercícios" in str(erro)
    else:
        raise AssertionError("PDF de um exercício deveria ser recusado.")


def testar_pdf_minimo_por_layout() -> None:
    cenarios = [
        ("PADRAO", [2024, 2025], "EXECUTIVO_ANALISTA"),
        ("FINANCEIRA", [2023, 2024, 2025], "ACADEMICO"),
    ]

    for layout, anos, modalidade in cenarios:
        contexto = montar_contexto_relatorio(
            **_objetos_oficiais(layout, anos),
            modalidade=modalidade,
        )
        resultado = gerar_pdf_financeiro(
            contexto,
            modalidade,
        )

        conteudo = resultado["conteudo"]
        assert isinstance(conteudo, bytes)
        assert conteudo.startswith(b"%PDF-")
        assert conteudo.rstrip().endswith(b"%%EOF")
        assert len(conteudo) > 2_000
        assert resultado["mime"] == MIME_PDF
        assert resultado["nome_arquivo"].startswith(
            "Sistema-CVM-COMPANHIA-DE-TESTE-S-A-"
        )
        assert resultado["nome_arquivo"].endswith(
            "-" + modalidade.lower().replace("_", "-") + ".pdf"
        )
        assert resultado["metadados"]["LAYOUT"] == layout
        assert resultado["metadados"]["PERIODO"] == (
            f"{anos[0]}-{anos[-1]}"
        )
        assert resultado["metadados"]["STATUS_VALIDACAO"] == "OK"
        assert b"PROTOTIPO" not in conteudo.upper()


def main() -> None:
    testar_contexto_temporal_e_sentinelas()
    testar_pdf_minimo_por_layout()
    print("RESULTADO: APROVADO - contexto e PDF minimo da C.2.")


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy
import re
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
    _estilos,
    _formatar_valor_demonstracao,
    _montar_tabela_demonstracao,
    gerar_pdf_financeiro,
)


def _demonstracao(
    layout: str,
    demonstracao: str,
    anos: list[int],
    quantidade_linhas: int = 6,
) -> pd.DataFrame:
    registros = []

    for ordem in range(1, quantidade_linhas + 1):
        tipo = "CABECALHO" if ordem == 2 else "DIRETA"
        registro = {
            "ORDEM": ordem,
            "LINHA": (
                "GRUPO CONTÁBIL"
                if tipo == "CABECALHO"
                else f"{ordem}.01 — Conta contábil de teste {ordem}"
            ),
            "TIPO": tipo,
        }

        for indice, ano in enumerate(anos):
            valor = float((ordem + indice) * 1_000)
            if ordem == 3:
                valor = 0.0
            elif ordem == 4:
                valor = -1_250.0
            elif ordem == 5:
                valor = pd.NA

            registro[f"VA_{ano}"] = valor
            registro[f"AV_{ano}"] = (
                pd.NA
                if layout == "FINANCEIRA" and demonstracao == "DRE"
                else (0.0 if ordem == 3 else -2.5 if ordem == 4 else 10.0)
            )
            registro[f"AH_{ano}"] = (
                pd.NA if ordem == 5 else 100.0 + indice
            )

        registros.append(registro)

    colunas = ["ORDEM", "LINHA", "TIPO"]
    for ano in reversed(anos):
        colunas.extend([f"VA_{ano}", f"AV_{ano}", f"AH_{ano}"])

    quadro = pd.DataFrame(registros)[colunas]
    quadro.attrs["DEMONSTRACAO"] = demonstracao
    quadro.attrs["ANO_BASE_AH"] = min(anos)
    quadro.attrs["ANOS"] = list(reversed(anos))
    quadro.attrs["LAYOUT"] = layout
    quadro.attrs["APRESENTACAO_SETORIAL"] = layout == "FINANCEIRA"
    quadro.attrs["AV_NAO_APLICAVEL"] = (
        layout == "FINANCEIRA" and demonstracao == "DRE"
    )
    return quadro


def _objetos_oficiais(layout: str, anos: list[int]) -> dict:
    base_oficial = pd.DataFrame(
        {
            "INDICADOR": ["ZERO", "AUSENTE", "NAO_APLICAVEL", "SINAL"],
            "VALOR": [0.0, "N/D", "N/A", -0.25],
        }
    )
    analise = base_oficial.copy(deep=True)
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
            demonstracao: _demonstracao(layout, demonstracao, anos)
            for demonstracao in ("BPA", "BPP", "DRE")
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


def testar_demonstracoes_sem_recalculo_ou_mutacao() -> None:
    for layout in ("PADRAO", "FINANCEIRA"):
        objetos = _objetos_oficiais(layout, [2023, 2024, 2025])
        originais = {
            chave: quadro.copy(deep=True)
            for chave, quadro in objetos["demonstracoes"].items()
        }
        contexto = montar_contexto_relatorio(
            **objetos,
            modalidade="EXECUTIVO_ANALISTA",
        )
        resultado = gerar_pdf_financeiro(contexto, "EXECUTIVO_ANALISTA")

        assert len(re.findall(rb"/Type\s*/Page(?!s)", resultado["conteudo"])) >= 5
        for chave, original in originais.items():
            pd.testing.assert_frame_equal(
                objetos["demonstracoes"][chave],
                original,
                check_flags=True,
            )
            assert objetos["demonstracoes"][chave].attrs == original.attrs


def testar_formatacao_e_tabela_multipagina() -> None:
    assert _formatar_valor_demonstracao(0.0, "VA") == "0"
    assert _formatar_valor_demonstracao(-1_250.0, "VA") == "(1.250)"
    assert _formatar_valor_demonstracao(pd.NA, "VA") == "N/D"
    assert _formatar_valor_demonstracao("N/A", "VA") == "N/A"
    assert _formatar_valor_demonstracao(-2.5, "AV") == "-2,50%"
    assert (
        _formatar_valor_demonstracao(
            pd.NA,
            "AV",
            av_nao_aplicavel=True,
        )
        == "N/A"
    )

    quadro = _demonstracao("FINANCEIRA", "DRE", [2023, 2024, 2025], 90)
    quadro.loc[0, "VA_2025"] = 3_066_169_000.0
    quadro.loc[0, "VA_2024"] = -248_171_000.0
    original = quadro.copy(deep=True)
    estilos = _estilos()
    tabela = _montar_tabela_demonstracao(quadro, estilos)

    assert tabela.repeatRows == 2
    assert sum(tabela._colWidths) <= 170 * 72 / 25.4 + 0.01
    assert len(tabela._cellvalues[0]) == 9
    assert tabela._cellvalues[0][1].text == "31/12/2025"
    assert tabela._cellvalues[1][1].text == "VA"
    assert tabela._cellvalues[1][2].text == "AV"
    assert tabela._cellvalues[1][3].text == "AH"
    assert tabela._cellvalues[2][1].text == "3.066.169.000"
    assert tabela._cellvalues[2][4].text == "(248.171.000)"
    largura_util_numerica = tabela._colWidths[1] - 3
    for coluna in (1, 4):
        _, altura = tabela._cellvalues[2][coluna].wrap(
            largura_util_numerica,
            100,
        )
        assert altura == estilos["numero_tabela"].leading
    assert tabela._cellvalues[2][2].text == "N/A"
    assert tabela._cellvalues[4][1].text == "0"
    assert tabela._cellvalues[5][1].text == "(1.250)"
    assert tabela._cellvalues[6][1].text == "N/D"
    pd.testing.assert_frame_equal(quadro, original, check_flags=True)
    assert quadro.attrs == original.attrs

    objetos = _objetos_oficiais("FINANCEIRA", [2023, 2024, 2025])
    objetos["demonstracoes"]["BPP"] = quadro
    contexto = montar_contexto_relatorio(
        **objetos,
        modalidade="EXECUTIVO_ANALISTA",
    )
    resultado = gerar_pdf_financeiro(contexto, "EXECUTIVO_ANALISTA")
    assert len(re.findall(rb"/Type\s*/Page(?!s)", resultado["conteudo"])) >= 8
    pd.testing.assert_frame_equal(quadro, original, check_flags=True)
    assert quadro.attrs == original.attrs


def main() -> None:
    testar_contexto_temporal_e_sentinelas()
    testar_pdf_minimo_por_layout()
    testar_demonstracoes_sem_recalculo_ou_mutacao()
    testar_formatacao_e_tabela_multipagina()
    print("RESULTADO: APROVADO - demonstracoes no PDF da C.3.")


if __name__ == "__main__":
    main()

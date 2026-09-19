from __future__ import annotations

import base64
from copy import deepcopy
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from src.contexto_relatorio import (  # noqa: E402
    montar_contexto_relatorio,
)
from src.graficos import (  # noqa: E402
    montar_graficos_financeiros_setoriais,
)
from src.indicadores import (  # noqa: E402
    FORMULAS as FORMULAS_PADRAO,
    ORDEM_INDICADORES,
)
from src.pdf_financeiro import (  # noqa: E402
    FIGURAS_PERMITIDAS_POR_LAYOUT,
    INDICADORES_POR_LAYOUT,
    MIME_PDF,
    PeriodoInsuficientePDF,
    _adicionar_apendice,
    _adicionar_narrativa,
    _estilos,
    _formatar_valor_indicador,
    _formatar_valor_demonstracao,
    _figura_para_png,
    _montar_tabela_indicadores,
    _montar_tabela_demonstracao,
    _montar_tabela_oficial,
    gerar_pdf_financeiro,
)
from src.relatorio import gerar_relatorio  # noqa: E402


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


GRUPOS_PADRAO = {
    "IPL": "Estrutura de Capital",
    "PCT": "Estrutura de Capital",
    "CE": "Estrutura de Capital",
    "EFSAT": "Estrutura de Capital",
    "LG": "Liquidez",
    "LC": "Liquidez",
    "LS": "Liquidez",
    "ICJ": "Liquidez",
    "GA": "Lucratividade/Desempenho",
    "RSV": "Lucratividade/Desempenho",
    "ROA": "Lucratividade/Desempenho",
    "ROE": "Lucratividade/Desempenho",
}

UNIDADES_PADRAO = {
    "IPL": "%", "PCT": "%", "CE": "%", "EFSAT": "%",
    "LG": "razão", "LC": "razão", "LS": "razão", "ICJ": "vezes",
    "GA": "vezes", "RSV": "%", "ROA": "%", "ROE": "%",
}

GRUPOS_FINANCEIRA = {
    "CAP_CONTABIL": "Capitalização e Funding",
    "PF_ATIVO": "Capitalização e Funding",
    "CRESC_ATIVO": "Crescimento",
    "CRESC_PL": "Crescimento",
    "CRESC_LL": "Crescimento",
    "RBI_ATIVO_MEDIO": "Intermediação e Rentabilidade",
    "PRETRIB_ATIVO_MEDIO": "Intermediação e Rentabilidade",
    "ROA": "Intermediação e Rentabilidade",
    "ROE": "Intermediação e Rentabilidade",
}


def _indicadores_oficiais(layout: str, anos: list[int]) -> dict:
    codigos = INDICADORES_POR_LAYOUT[layout]
    grupos = GRUPOS_PADRAO if layout == "PADRAO" else GRUPOS_FINANCEIRA
    unidades = (
        UNIDADES_PADRAO
        if layout == "PADRAO"
        else {codigo: "%" for codigo in codigos}
    )
    analise = pd.DataFrame(
        [
            {
                "GRUPO": grupos[codigo],
                "INDICADOR": codigo,
                "NOME": f"Indicador oficial {codigo}",
                "DELTA": (
                    "+1,00 p.p."
                    if indice == 0
                    else "-0,25 p.p."
                    if indice == 1
                    else "N/D"
                ),
            }
            for indice, codigo in enumerate(codigos)
        ]
    )

    if layout == "PADRAO":
        registros = []
        for indice, codigo in enumerate(codigos):
            registro = {
                "GRUPO": grupos[codigo],
                "INDICADOR": codigo,
                "UNIDADE": unidades[codigo],
                "APLICABILIDADE": "APLICAVEL",
            }
            for posicao, ano in enumerate(anos):
                registro[ano] = (indice + 1) / 100 + posicao / 100
            registros.append(registro)
        base_oficial = pd.DataFrame(registros)
        base_oficial[anos] = base_oficial[anos].astype(object)
        base_oficial.loc[0, anos[0]] = 0.0
        base_oficial.loc[1, anos[0]] = -0.25
        base_oficial.loc[2, anos[0]] = "N/D"
        base_oficial.loc[3, anos[0]] = "N/A"
    else:
        registros = []
        for indice, codigo in enumerate(codigos):
            for posicao, ano in enumerate(anos):
                valor = (indice + 1) / 100 + posicao / 100
                status = "OK"
                if indice == 0 and posicao == 0:
                    valor = 0.0
                elif indice == 1 and posicao == 0:
                    valor = -0.25
                elif indice == 2 and posicao == 0:
                    valor = pd.NA
                    status = "N/D"
                elif indice == 3 and posicao == 0:
                    valor = pd.NA
                    status = "N/A"
                registros.append(
                    {
                        "ANO": ano,
                        "GRUPO": grupos[codigo],
                        "INDICADOR": codigo,
                        "NOME": f"Indicador oficial {codigo}",
                        "UNIDADE": unidades[codigo],
                        "VALOR": valor,
                        "STATUS": status,
                    }
                )
        base_oficial = pd.DataFrame(registros)

    return {"ANALISE": analise, "BASE_OFICIAL": base_oficial}


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
    indicadores = _indicadores_oficiais(layout, anos)
    narrativa = None
    if len(anos) >= 2:
        narrativa = {
            "RESUMO_EXECUTIVO": (
                "A análise oficial preserva acentuação, "
                "sinais e limitações metodológicas."
            ),
            "SINTESES_GRUPOS": {
                "Grupo oficial": "Leitura integrada oficial do grupo."
            },
            "PRINCIPAIS_MUDANCAS": [
                "Mudança oficial com zero 0, N/D e N/A preservados."
            ],
            "PONTOS_ATENCAO": ["Ponto de atenção oficial."],
            "CONCLUSAO": (
                "Conclusão oficial do relatório com DuPont textual PADRAO."
                if layout == "PADRAO"
                else "Conclusão oficial do relatório."
            ),
            "DUPONT": (
                pd.DataFrame([{"COMPONENTE": "DuPont oficial PADRAO"}])
                if layout == "PADRAO"
                else pd.DataFrame()
            ),
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
        "indicadores": indicadores,
        "narrativa": narrativa,
        "status_validacao": "OK",
        "validacao": pd.DataFrame(
            [{"TESTE": "Sentinelas", "STATUS": "OK"}]
        ),
        "metodologia": {
            "LAYOUT": layout,
            "REGRA_OFICIAL": f"Metodologia oficial {layout}",
        },
        "fontes": pd.DataFrame(
            [{"FONTE": "CVM", "REFERENCIA": "Fonte oficial do exercício"}]
        ),
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

            base = contexto["INDICADORES"]["BASE_OFICIAL"]
            if layout == "PADRAO":
                assert base.loc[0, anos[0]] == 0.0
                assert base.loc[1, anos[0]] == -0.25
                assert base.loc[2, anos[0]] == "N/D"
                assert base.loc[3, anos[0]] == "N/A"
            else:
                primeiro_ano = base[base["ANO"] == anos[0]]
                assert primeiro_ano["VALOR"].iloc[0] == 0.0
                assert primeiro_ano["VALOR"].iloc[1] == -0.25
                assert primeiro_ano["STATUS"].iloc[2] == "N/D"
                assert primeiro_ano["STATUS"].iloc[3] == "N/A"
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


def testar_indicadores_por_layout_sem_recalculo() -> None:
    assert _formatar_valor_indicador(0.0, "%", "OK") == "0,00%"
    assert _formatar_valor_indicador(-0.25, "%", "OK") == "-25,00%"
    assert _formatar_valor_indicador(pd.NA, "%", "N/D") == "N/D"
    assert _formatar_valor_indicador(pd.NA, "%", "N/A") == "N/A"

    for layout in ("PADRAO", "FINANCEIRA"):
        anos = [2023, 2024, 2025]
        indicadores = _indicadores_oficiais(layout, anos)
        original_analise = indicadores["ANALISE"].copy(deep=True)
        original_base = indicadores["BASE_OFICIAL"].copy(deep=True)
        tabela = _montar_tabela_indicadores(
            indicadores,
            layout,
            anos,
            _estilos(),
        )

        assert tabela.repeatRows == 1
        assert sum(tabela._colWidths) <= 170 * 72 / 25.4 + 0.01
        textos = [
            celula.getPlainText()
            for linha in tabela._cellvalues
            for celula in linha
            if isinstance(celula, type(tabela._cellvalues[0][0]))
        ]
        for codigo in INDICADORES_POR_LAYOUT[layout]:
            assert any(codigo in texto for texto in textos)

        if layout == "FINANCEIRA":
            incompatíveis = set(INDICADORES_POR_LAYOUT["PADRAO"]) - {
                "ROA", "ROE"
            }
            for codigo in incompatíveis:
                assert not any(
                    texto == codigo or texto.endswith(" " + codigo)
                    for texto in textos
                )

        linhas_indicadores = [
            linha
            for linha in tabela._cellvalues
            if hasattr(linha[0], "getPlainText")
            and any(
                codigo in linha[0].getPlainText()
                for codigo in INDICADORES_POR_LAYOUT[layout]
            )
        ]
        assert len(linhas_indicadores) == len(INDICADORES_POR_LAYOUT[layout])
        assert linhas_indicadores[0][2].getPlainText() == "0,00%"
        assert linhas_indicadores[1][2].getPlainText() == "-25,00%"
        assert linhas_indicadores[2][2].getPlainText() == "N/D"
        assert linhas_indicadores[3][2].getPlainText() == "N/A"
        assert linhas_indicadores[0][-1].getPlainText() == "+1,00 p.p."
        assert linhas_indicadores[1][-1].getPlainText() == "-0,25 p.p."

        pd.testing.assert_frame_equal(
            indicadores["ANALISE"],
            original_analise,
            check_flags=True,
        )
        pd.testing.assert_frame_equal(
            indicadores["BASE_OFICIAL"],
            original_base,
            check_flags=True,
        )

        sem_delta = deepcopy(indicadores)
        sem_delta["ANALISE"] = sem_delta["ANALISE"].drop(columns="DELTA")
        tabela_sem_delta = _montar_tabela_indicadores(
            sem_delta,
            layout,
            anos,
            _estilos(),
        )
        assert len(tabela_sem_delta._cellvalues[0]) == 2 + len(anos)
        assert all(
            not (
                hasattr(celula, "getPlainText")
                and celula.getPlainText() == "Variação"
            )
            for celula in tabela_sem_delta._cellvalues[0]
        )


def testar_graficos_financeiros_sem_recalculo() -> None:
    anos = [2023, 2024, 2025]
    base = _indicadores_oficiais(
        "FINANCEIRA",
        anos,
    )["BASE_OFICIAL"]
    original = base.copy(deep=True)
    graficos = montar_graficos_financeiros_setoriais(base, anos)

    assert set(graficos) == {
        "capitalizacao_funding",
        "crescimento",
        "intermediacao",
    }
    assert [
        traco.name
        for traco in graficos["capitalizacao_funding"].data
    ] == ["CAP_CONTABIL", "PF_ATIVO"]
    assert [
        traco.name
        for traco in graficos["crescimento"].data
    ] == ["CRESC_ATIVO", "CRESC_PL", "CRESC_LL"]
    assert [
        traco.name
        for traco in graficos["intermediacao"].data
    ] == ["RBI_ATIVO_MEDIO", "PRETRIB_ATIVO_MEDIO"]

    crescimento = {
        traco.name: traco
        for traco in graficos["crescimento"].data
    }
    assert pd.isna(crescimento["CRESC_ATIVO"].y[0])
    assert "2023" not in crescimento["CRESC_PL"].x
    assert crescimento["CRESC_LL"].y[0] == 5.0
    pd.testing.assert_frame_equal(base, original, check_flags=True)


def testar_figuras_no_pdf_por_layout() -> None:
    figura = go.Figure(
        go.Scatter(
            x=["2023", "2024", "2025"],
            y=[1.0, None, -2.0],
            mode="lines+markers",
        )
    )
    png = _figura_para_png(figura)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")

    proibida_por_layout = {
        "PADRAO": "capitalizacao_funding",
        "FINANCEIRA": "estrutura",
    }
    for layout in ("PADRAO", "FINANCEIRA"):
        objetos = _objetos_oficiais(layout, [2023, 2024, 2025])
        objetos["figuras"] = {
            chave: PNG_1X1
            for chave in FIGURAS_PERMITIDAS_POR_LAYOUT[layout]
        }
        objetos["figuras"][proibida_por_layout[layout]] = b"INVALIDO"
        contexto = montar_contexto_relatorio(
            **objetos,
            modalidade="EXECUTIVO_ANALISTA",
        )
        resultado = gerar_pdf_financeiro(
            contexto,
            "EXECUTIVO_ANALISTA",
        )
        assert resultado["conteudo"].startswith(b"%PDF-")
        assert len(
            re.findall(rb"/Type\s*/Page(?!s)", resultado["conteudo"])
        ) >= 8


def _textos_fluxo(itens: list) -> list[str]:
    textos = []
    for item in itens:
        if hasattr(item, "getPlainText"):
            textos.append(item.getPlainText())
        elif hasattr(item, "_cellvalues"):
            for linha in item._cellvalues:
                textos.extend(_textos_fluxo(list(linha)))
        elif hasattr(item, "_content"):
            textos.extend(_textos_fluxo(list(item._content)))
        elif isinstance(item, str):
            textos.append(item)
    return textos


def testar_narrativa_metodologia_validacao_e_fontes() -> None:
    for layout in ("PADRAO", "FINANCEIRA"):
        objetos = _objetos_oficiais(layout, [2023, 2024, 2025])
        objetos["status_validacao"] = "BLOQUEIO"
        objetos["validacao"] = pd.DataFrame(
            [
                {
                    "CATEGORIA": "Integridade",
                    "ANO": 2025,
                    "TESTE": "Sentinela N/D",
                    "STATUS": "ALERTA",
                    "DETALHE": "N/D preservado pela validação oficial.",
                },
                {
                    "CATEGORIA": "Metodologia",
                    "ANO": 2025,
                    "TESTE": "Sentinela N/A",
                    "STATUS": "BLOQUEIO",
                    "DETALHE": "N/A preservado pela validação oficial.",
                },
            ]
        )
        originais = deepcopy(objetos)
        contexto = montar_contexto_relatorio(
            **objetos,
            modalidade="EXECUTIVO_ANALISTA",
        )
        resultado = gerar_pdf_financeiro(contexto, "EXECUTIVO_ANALISTA")
        assert resultado["conteudo"].startswith(b"%PDF-")
        fluxo = []
        _adicionar_narrativa(
            fluxo,
            contexto["NARRATIVA"],
            layout,
            _estilos(),
        )
        _adicionar_apendice(fluxo, contexto, _estilos())
        texto = "\n".join(_textos_fluxo(fluxo))

        for trecho in (
            "Grupo oficial",
            "Leitura integrada oficial do grupo.",
            "Mudança oficial com zero 0, N/D e N/A preservados.",
            "Ponto de atenção oficial.",
            "Conclusão oficial do relatório",
            f"Metodologia oficial {layout}",
            "ALERTA",
            "BLOQUEIO",
            "N/D preservado pela validação oficial.",
            "N/A preservado pela validação oficial.",
            "Fonte oficial do exercício",
        ):
            assert trecho in texto

        assert "DuPont oficial PADRAO" not in texto
        if layout == "PADRAO":
            assert "DuPont textual PADRAO" in texto
        else:
            assert "DuPont textual PADRAO" not in texto

        pd.testing.assert_frame_equal(
            objetos["validacao"],
            originais["validacao"],
        )
        pd.testing.assert_frame_equal(
            objetos["fontes"],
            originais["fontes"],
        )
        assert objetos["narrativa"].keys() == originais["narrativa"].keys()

    objetos = _objetos_oficiais("FINANCEIRA", [2024, 2025])
    objetos["narrativa"].pop("PONTOS_ATENCAO")
    contexto = montar_contexto_relatorio(
        **objetos,
        modalidade="EXECUTIVO_ANALISTA",
    )
    fluxo = []
    _adicionar_narrativa(
        fluxo,
        contexto["NARRATIVA"],
        "FINANCEIRA",
        _estilos(),
    )
    texto = "\n".join(_textos_fluxo(fluxo))
    assert "Pontos de atenção" not in texto


def testar_metodologia_padrao_e_paginacao_validacao() -> None:
    relatorio = gerar_relatorio(
        "004170",
        "VALE S.A.",
        [2023, 2024, 2025],
    )
    metodologia = relatorio["METODOLOGIA"]
    assert metodologia["LAYOUT"] == "PADRAO"
    assert metodologia["ANALISE_HORIZONTAL"][1] == "Ano-base = 2023 = 100."
    indicadores = metodologia["INDICADORES"]
    assert indicadores["INDICADOR"].tolist() == ORDEM_INDICADORES
    assert dict(
        zip(indicadores["INDICADOR"], indicadores["FORMULA"])
    ) == FORMULAS_PADRAO

    validacao = pd.DataFrame(
        [
            {
                "CATEGORIA": "Integridade",
                "ANO": 2025,
                "TESTE": f"Teste {indice}",
                "STATUS": "OK",
                "DETALHE": "Linha oficial preservada.",
            }
            for indice in range(77)
        ]
    )
    tabela = _montar_tabela_oficial(
        validacao,
        _estilos(),
        evitar_linha_orfa=True,
    )
    assert tabela._rowSplitRange == (1, -2)
    assert len(tabela._cellvalues) == 78

    historia = []
    _adicionar_apendice(
        historia,
        {
            "METODOLOGIA": None,
            "VALIDACAO": {
                "STATUS_GERAL": "OK",
                "TABELA": validacao,
            },
            "FONTES": None,
        },
        _estilos(),
    )
    tabelas = [item for item in historia if hasattr(item, "_cellvalues")]
    assert [len(item._cellvalues) - 1 for item in tabelas] == [26, 26, 25]
    assert sum(len(item._cellvalues) - 1 for item in tabelas) == 77


def main() -> None:
    testar_contexto_temporal_e_sentinelas()
    testar_pdf_minimo_por_layout()
    testar_demonstracoes_sem_recalculo_ou_mutacao()
    testar_formatacao_e_tabela_multipagina()
    testar_indicadores_por_layout_sem_recalculo()
    testar_graficos_financeiros_sem_recalculo()
    testar_figuras_no_pdf_por_layout()
    testar_narrativa_metodologia_validacao_e_fontes()
    testar_metodologia_padrao_e_paginacao_validacao()
    print("RESULTADO: APROVADO - narrativa e apêndices no PDF da C.6.")


if __name__ == "__main__":
    main()

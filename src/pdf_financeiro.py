from __future__ import annotations

from html import escape
from io import BytesIO
import math
import re
import unicodedata
from typing import Any, Mapping

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    LongTable,
    Table,
    TableStyle,
)

from src.contexto_relatorio import (
    ErroContextoRelatorio,
    MODALIDADES_SUPORTADAS,
    validar_contexto_relatorio,
)


AZUL_ESCURO = colors.HexColor("#1F3B63")
AZUL_TEXTO = colors.HexColor("#213D63")
CINZA_FUNDO = colors.HexColor("#F2F5F8")
CINZA_BORDA = colors.HexColor("#D5DCE5")
CINZA_TEXTO = colors.HexColor("#5F6E86")

MIME_PDF = "application/pdf"

ROTULOS_MODALIDADE = {
    "EXECUTIVO_ANALISTA": "Executivo / Analista",
    "ACADEMICO": "Acadêmico",
}

INDICADORES_POR_LAYOUT = {
    "PADRAO": [
        "IPL", "PCT", "CE", "EFSAT", "LG", "LC",
        "LS", "ICJ", "GA", "RSV", "ROA", "ROE",
    ],
    "FINANCEIRA": [
        "CAP_CONTABIL", "PF_ATIVO", "CRESC_ATIVO", "CRESC_PL",
        "CRESC_LL", "RBI_ATIVO_MEDIO", "PRETRIB_ATIVO_MEDIO",
        "ROA", "ROE",
    ],
}


class PeriodoInsuficientePDF(ValueError):
    """O contexto existe, mas não admite PDF comparativo."""


def _normalizar_modalidade(modalidade: str) -> str:
    valor = str(modalidade).strip().upper().replace(" ", "_")
    valor = valor.replace("/", "_")

    if valor not in MODALIDADES_SUPORTADAS:
        raise ErroContextoRelatorio(
            "Modalidade deve ser EXECUTIVO_ANALISTA ou ACADEMICO."
        )

    return valor


def _nome_seguro(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", str(texto))
    ascii_texto = normalizado.encode("ascii", "ignore").decode("ascii")
    seguro = re.sub(r"[^A-Za-z0-9]+", "-", ascii_texto).strip("-")
    return seguro or "companhia"


def _resumo_oficial(contexto: Mapping[str, Any]) -> str:
    narrativa = contexto["NARRATIVA"]

    if isinstance(narrativa, Mapping):
        resumo = narrativa.get("RESUMO_EXECUTIVO")
    else:
        resumo = narrativa

    if resumo is None or not str(resumo).strip():
        raise ErroContextoRelatorio(
            "O contexto não contém RESUMO_EXECUTIVO oficial."
        )

    return str(resumo).strip()


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "marca": ParagraphStyle(
            "Marca",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=AZUL_ESCURO,
            spaceAfter=16 * mm,
        ),
        "titulo_capa": ParagraphStyle(
            "TituloCapa",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=28,
            alignment=TA_CENTER,
            textColor=AZUL_ESCURO,
            spaceAfter=10 * mm,
        ),
        "empresa": ParagraphStyle(
            "Empresa",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=20,
            textColor=AZUL_TEXTO,
            spaceAfter=2 * mm,
        ),
        "modalidade": ParagraphStyle(
            "Modalidade",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=14,
            textColor=CINZA_TEXTO,
            spaceAfter=18 * mm,
        ),
        "titulo": ParagraphStyle(
            "TituloSecao",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=AZUL_ESCURO,
            spaceAfter=7 * mm,
        ),
        "corpo": ParagraphStyle(
            "Corpo",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#172033"),
            spaceAfter=5 * mm,
        ),
        "nota_tabela": ParagraphStyle(
            "NotaTabela",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            textColor=CINZA_TEXTO,
            spaceAfter=3 * mm,
        ),
        "cabecalho_tabela": ParagraphStyle(
            "CabecalhoTabela",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8,
            alignment=TA_CENTER,
            textColor=colors.white,
        ),
        "descricao_tabela": ParagraphStyle(
            "DescricaoTabela",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=8.2,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#172033"),
        ),
        "descricao_tabela_negrito": ParagraphStyle(
            "DescricaoTabelaNegrito",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8.2,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#172033"),
        ),
        "numero_tabela": ParagraphStyle(
            "NumeroTabela",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.2,
            leading=8,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#172033"),
            splitLongWords=False,
        ),
        "indicador_tabela": ParagraphStyle(
            "IndicadorTabela",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=8.2,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#172033"),
        ),
        "grupo_indicador": ParagraphStyle(
            "GrupoIndicador",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=8.5,
            alignment=TA_LEFT,
            textColor=AZUL_TEXTO,
        ),
    }


def _eh_ausente(valor: Any) -> bool:
    if valor is None:
        return True

    texto = str(valor).strip().lower()
    if texto in {"<na>", "nan", "nat", "none"}:
        return True

    try:
        return math.isnan(float(valor))
    except (TypeError, ValueError):
        return False


def _formatar_numero_br(valor: float, casas: int) -> str:
    texto = f"{abs(valor):,.{casas}f}"
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"({texto})" if valor < 0 else texto


def _formatar_valor_demonstracao(
    valor: Any,
    metrica: str,
    *,
    av_nao_aplicavel: bool = False,
) -> str:
    if metrica == "AV" and av_nao_aplicavel:
        return "N/A"

    if isinstance(valor, str):
        sentinela = valor.strip().upper()
        if sentinela in {"N/D", "N/A"}:
            return sentinela

    if _eh_ausente(valor):
        return "N/D"

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)

    if metrica == "VA":
        casas = 0 if numero.is_integer() else 2
        return _formatar_numero_br(numero, casas)

    sinal = "-" if numero < 0 else ""
    percentual = f"{abs(numero):.2f}".replace(".", ",")
    return f"{sinal}{percentual}%"


def _anos_demonstracao(quadro: Any) -> list[str]:
    return [
        str(coluna)[3:]
        for coluna in quadro.columns
        if str(coluna).startswith("VA_")
    ]


def _montar_tabela_demonstracao(
    quadro: Any,
    estilos: Mapping[str, ParagraphStyle],
) -> LongTable:
    copia = quadro.copy(deep=True)
    if "ORDEM" in copia.columns:
        copia = copia.sort_values("ORDEM", kind="stable")

    anos = _anos_demonstracao(copia)
    ano_base = str(copia.attrs.get("ANO_BASE_AH", ""))
    av_nao_aplicavel = bool(copia.attrs.get("AV_NAO_APLICAVEL", False))

    metricas_por_ano = {
        ano: [
            metrica
            for metrica in ("VA", "AV", "AH")
            if metrica != "AH" or ano != ano_base
        ]
        for ano in anos
    }

    cabecalho_anos = [
        Paragraph("Conta", estilos["cabecalho_tabela"]),
    ]
    cabecalho_metricas = [""]
    comandos_estilo = [
        ("SPAN", (0, 0), (0, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), AZUL_ESCURO),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, CINZA_BORDA),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (1, 2), (-1, -1), 1.5),
        ("RIGHTPADDING", (1, 2), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]

    coluna_atual = 1
    for ano in anos:
        metricas = metricas_por_ano[ano]
        cabecalho_anos.append(
            Paragraph(f"31/12/{escape(ano)}", estilos["cabecalho_tabela"])
        )
        cabecalho_anos.extend([""] * (len(metricas) - 1))
        cabecalho_metricas.extend(
            Paragraph(metrica, estilos["cabecalho_tabela"])
            for metrica in metricas
        )
        comandos_estilo.append(
            (
                "SPAN",
                (coluna_atual, 0),
                (coluna_atual + len(metricas) - 1, 0),
            )
        )
        coluna_atual += len(metricas)

    dados = [cabecalho_anos, cabecalho_metricas]
    tipos = []

    for _, registro in copia.iterrows():
        tipo = str(registro.get("TIPO", "")).strip().upper()
        tipos.append(tipo)
        estilo_descricao = (
            estilos["descricao_tabela_negrito"]
            if tipo in {"CABECALHO", "SOMA"}
            else estilos["descricao_tabela"]
        )
        linha = [
            Paragraph(escape(str(registro.get("LINHA", ""))), estilo_descricao)
        ]

        for ano in anos:
            for metrica in metricas_por_ano[ano]:
                if tipo == "CABECALHO":
                    texto = "-"
                elif tipo == "SEM_CODIGO":
                    texto = "N/D"
                else:
                    texto = _formatar_valor_demonstracao(
                        registro.get(f"{metrica}_{ano}"),
                        metrica,
                        av_nao_aplicavel=(
                            metrica == "AV" and av_nao_aplicavel
                        ),
                    )
                linha.append(Paragraph(escape(texto), estilos["numero_tabela"]))

        dados.append(linha)

    quantidade_numericas = sum(len(valor) for valor in metricas_por_ano.values())
    largura_descricao = 47 * mm
    largura_numerica = (123 * mm) / max(quantidade_numericas, 1)
    tabela = LongTable(
        dados,
        colWidths=[largura_descricao] + [largura_numerica] * quantidade_numericas,
        repeatRows=2,
        splitByRow=1,
        hAlign="LEFT",
    )

    for indice, tipo in enumerate(tipos, start=2):
        if tipo == "CABECALHO":
            comandos_estilo.append(
                ("BACKGROUND", (0, indice), (-1, indice), colors.HexColor("#E4EBF3"))
            )
        elif indice % 2:
            comandos_estilo.append(
                ("BACKGROUND", (0, indice), (-1, indice), CINZA_FUNDO)
            )

    tabela.setStyle(TableStyle(comandos_estilo))
    return tabela


def _adicionar_demonstracoes(
    historia: list[Any],
    contexto: Mapping[str, Any],
    estilos: Mapping[str, ParagraphStyle],
) -> None:
    titulos = {
        "BPA": "Balanço Patrimonial - Ativo",
        "BPP": "Balanço Patrimonial - Passivo",
        "DRE": "Demonstração do Resultado",
    }
    maximo_linhas_por_pagina = 24

    for chave in ("BPA", "BPP", "DRE"):
        quadro = contexto["DEMONSTRACOES"][chave]
        av_nao_aplicavel = bool(
            quadro.attrs.get("AV_NAO_APLICAVEL", False)
        )
        nota = (
            "Valores absolutos em R$ mil. VA = Valor Absoluto; "
            "AV = N/A para esta demonstração; AH = Análise Horizontal."
            if av_nao_aplicavel
            else "Valores absolutos em R$ mil. VA = Valor Absoluto; "
            "AV = Análise Vertical; AH = Análise Horizontal."
        )
        historia.extend(
            [
                PageBreak(),
                Paragraph(titulos[chave], estilos["titulo"]),
                Paragraph(
                    nota,
                    estilos["nota_tabela"],
                ),
            ]
        )

        if quadro.empty:
            historia.append(
                Paragraph("Demonstração não disponível.", estilos["corpo"])
            )
        else:
            copia = quadro.copy(deep=True)
            if "ORDEM" in copia.columns:
                copia = copia.sort_values("ORDEM", kind="stable")

            for inicio in range(0, len(copia), maximo_linhas_por_pagina):
                if inicio:
                    historia.append(PageBreak())

                trecho = copia.iloc[
                    inicio:inicio + maximo_linhas_por_pagina
                ].copy(deep=True)
                trecho.attrs = dict(copia.attrs)
                historia.append(_montar_tabela_demonstracao(trecho, estilos))


def _primeiro_registro(quadro: Any, indicador: str) -> Any:
    if quadro is None or not hasattr(quadro, "columns"):
        return None
    if "INDICADOR" not in quadro.columns:
        return None

    registros = quadro[
        quadro["INDICADOR"].astype(str) == str(indicador)
    ]
    if registros.empty:
        return None
    return registros.iloc[0]


def _texto_oficial(registro: Any, coluna: str) -> str | None:
    if registro is None or coluna not in registro.index:
        return None
    valor = registro[coluna]
    if _eh_ausente(valor):
        return None
    return str(valor).strip()


def _valor_indicador_oficial(
    base_oficial: Any,
    indicador: str,
    ano: Any,
) -> tuple[Any, str | None]:
    if "ANO" in base_oficial.columns and "VALOR" in base_oficial.columns:
        registros = base_oficial[
            (base_oficial["INDICADOR"].astype(str) == str(indicador))
            & (base_oficial["ANO"].astype(str) == str(ano))
        ]
        if registros.empty:
            return None, None
        registro = registros.iloc[0]
        status = _texto_oficial(registro, "STATUS")
        return registro["VALOR"], status

    registro = _primeiro_registro(base_oficial, indicador)
    if registro is None:
        return None, None

    coluna_ano = next(
        (
            coluna
            for coluna in base_oficial.columns
            if str(coluna) == str(ano)
        ),
        None,
    )
    valor = registro[coluna_ano] if coluna_ano is not None else None
    status = _texto_oficial(registro, f"STATUS_{ano}")
    if status is None and _texto_oficial(
        registro,
        "APLICABILIDADE",
    ) == "NAO_APLICAVEL":
        status = "N/A"
    return valor, status


def _formatar_valor_indicador(
    valor: Any,
    unidade: str,
    status: str | None = None,
) -> str:
    status_normalizado = str(status or "").strip().upper()
    if status_normalizado in {"N/D", "N/A"}:
        return status_normalizado

    if isinstance(valor, str):
        sentinela = valor.strip().upper()
        if sentinela in {"N/D", "N/A"}:
            return sentinela

    if _eh_ausente(valor):
        return "N/D"

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)

    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    if str(unidade).strip() == "%":
        percentual = f"{numero * 100:,.2f}"
        percentual = (
            percentual.replace(",", "_").replace(".", ",").replace("_", ".")
        )
        return percentual + "%"
    return texto


def _montar_tabela_indicadores(
    indicadores: Mapping[str, Any],
    layout: str,
    anos: list[Any],
    estilos: Mapping[str, ParagraphStyle],
) -> LongTable:
    analise = indicadores["ANALISE"]
    base_oficial = indicadores["BASE_OFICIAL"]
    esperados = INDICADORES_POR_LAYOUT.get(str(layout).upper())
    if esperados is None:
        raise ErroContextoRelatorio(
            f"Layout sem contrato de indicadores no PDF: {layout}."
        )

    for nome_quadro, quadro in (
        ("ANALISE", analise),
        ("BASE_OFICIAL", base_oficial),
    ):
        codigos_disponiveis = (
            set(quadro["INDICADOR"].dropna().astype(str).tolist())
            if hasattr(quadro, "columns") and "INDICADOR" in quadro.columns
            else set()
        )
        ausentes = [
            codigo for codigo in esperados if codigo not in codigos_disponiveis
        ]
        if ausentes:
            raise ErroContextoRelatorio(
                f"Indicadores oficiais ausentes de {nome_quadro}: "
                + ", ".join(ausentes)
            )

    exibir_delta = hasattr(analise, "columns") and "DELTA" in analise.columns
    cabecalho = [
        Paragraph("Indicador", estilos["cabecalho_tabela"]),
        Paragraph("Unidade", estilos["cabecalho_tabela"]),
        *(
            Paragraph(escape(str(ano)), estilos["cabecalho_tabela"])
            for ano in anos
        ),
    ]
    if exibir_delta:
        cabecalho.append(
            Paragraph("Variação", estilos["cabecalho_tabela"])
        )

    dados = [cabecalho]
    linhas_grupo = []
    grupo_anterior = None

    for codigo in esperados:
        registro_analise = _primeiro_registro(analise, codigo)
        registro_base = _primeiro_registro(base_oficial, codigo)
        grupo = (
            _texto_oficial(registro_analise, "GRUPO")
            or _texto_oficial(registro_base, "GRUPO")
            or "Indicadores"
        )
        if grupo != grupo_anterior:
            linhas_grupo.append(len(dados))
            dados.append(
                [
                    Paragraph(escape(grupo), estilos["grupo_indicador"]),
                    *("" for _ in range(len(cabecalho) - 1)),
                ]
            )
            grupo_anterior = grupo

        nome = (
            _texto_oficial(registro_analise, "NOME")
            or _texto_oficial(registro_base, "NOME")
            or codigo
        )
        unidade = (
            _texto_oficial(registro_base, "UNIDADE")
            or _texto_oficial(registro_analise, "UNIDADE")
            or ""
        )
        linha = [
            Paragraph(
                f"{escape(nome)}<br/><font size='6' color='#5F6E86'>"
                f"{escape(codigo)}</font>",
                estilos["indicador_tabela"],
            ),
            Paragraph(escape(unidade), estilos["numero_tabela"]),
        ]
        for ano in anos:
            valor, status = _valor_indicador_oficial(
                base_oficial,
                codigo,
                ano,
            )
            linha.append(
                Paragraph(
                    escape(_formatar_valor_indicador(valor, unidade, status)),
                    estilos["numero_tabela"],
                )
            )

        if exibir_delta:
            delta = (
                registro_analise["DELTA"]
                if registro_analise is not None
                else None
            )
            texto_delta = "N/D" if _eh_ausente(delta) else str(delta)
            linha.append(
                Paragraph(escape(texto_delta), estilos["numero_tabela"])
            )
        dados.append(linha)

    largura_indicador = 52 * mm
    largura_unidade = 18 * mm
    largura_delta = 28 * mm if exibir_delta else 0
    largura_anos = 170 * mm - largura_indicador - largura_unidade - largura_delta
    largura_ano = largura_anos / max(len(anos), 1)
    larguras = [largura_indicador, largura_unidade]
    larguras.extend([largura_ano] * len(anos))
    if exibir_delta:
        larguras.append(largura_delta)

    comandos = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for linha_grupo in linhas_grupo:
        comandos.extend(
            [
                ("SPAN", (0, linha_grupo), (-1, linha_grupo)),
                ("BACKGROUND", (0, linha_grupo), (-1, linha_grupo), colors.HexColor("#E4EBF3")),
            ]
        )

    tabela = LongTable(
        dados,
        colWidths=larguras,
        repeatRows=1,
        splitByRow=1,
        hAlign="LEFT",
    )
    tabela.setStyle(TableStyle(comandos))
    return tabela


def _adicionar_indicadores(
    historia: list[Any],
    indicadores: Mapping[str, Any],
    layout: str,
    anos: list[Any],
    estilos: Mapping[str, ParagraphStyle],
) -> None:
    historia.extend(
        [
            PageBreak(),
            Paragraph("Indicadores", estilos["titulo"]),
            Paragraph(
                "Valores e variações conforme os objetos oficiais do relatório.",
                estilos["nota_tabela"],
            ),
            _montar_tabela_indicadores(
                indicadores,
                layout,
                anos,
                estilos,
            ),
        ]
    )


def _configurar_metadados(canvas, documento, metadados: Mapping[str, Any]) -> None:
    canvas.setTitle("Relatório Financeiro Profissional")
    canvas.setAuthor("Sistema CVM")
    canvas.setSubject(
        "Análise financeira de " + str(metadados["DENOM_CIA"])
    )
    canvas.setCreator("Sistema CVM")


def _pagina_interna(canvas, documento, metadados: Mapping[str, Any]) -> None:
    _configurar_metadados(canvas, documento, metadados)
    canvas.saveState()
    largura, _ = A4
    canvas.setStrokeColor(CINZA_BORDA)
    canvas.line(18 * mm, 14 * mm, largura - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(CINZA_TEXTO)
    rodape = (
        "Sistema CVM - Relatório Financeiro Profissional | "
        f"{metadados['DENOM_CIA']} | {metadados['PERIODO']}"
    )
    canvas.drawString(18 * mm, 9 * mm, rodape)
    canvas.drawRightString(
        largura - 18 * mm,
        9 * mm,
        f"Página {documento.page}",
    )
    canvas.restoreState()


def gerar_pdf_financeiro(
    contexto: Mapping[str, Any],
    modalidade: str,
) -> dict[str, Any]:
    """Gera o PDF financeiro a partir do contexto oficial, sem recalcular dados."""
    validar_contexto_relatorio(contexto)
    modalidade_normalizada = _normalizar_modalidade(modalidade)

    periodo = contexto["PERIODO"]
    if periodo["MODO_TEMPORAL"] == "PERIODO_INSUFICIENTE":
        raise PeriodoInsuficientePDF(
            "A exportação PDF exige pelo menos dois exercícios."
        )

    identificacao = contexto["IDENTIFICACAO"]
    if modalidade_normalizada != identificacao["MODALIDADE"]:
        raise ErroContextoRelatorio(
            "A modalidade solicitada diverge da modalidade do contexto."
        )

    resumo = _resumo_oficial(contexto)
    anos = periodo["ANOS_USADOS"]
    periodo_texto = f"{anos[0]}-{anos[-1]}"

    metadados = {
        "VERSAO_CONTRATO": contexto["VERSAO_CONTRATO"],
        "DENOM_CIA": identificacao["DENOM_CIA"],
        "CD_CVM": identificacao["CD_CVM"],
        "PERIODO": periodo_texto,
        "LAYOUT": identificacao["LAYOUT"],
        "MODALIDADE": modalidade_normalizada,
        "STATUS_VALIDACAO": contexto["VALIDACAO"]["STATUS_GERAL"],
    }

    memoria = BytesIO()
    documento = SimpleDocTemplate(
        memoria,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="Relatório Financeiro Profissional",
        author="Sistema CVM",
    )
    estilos = _estilos()

    historia = [
        Spacer(1, 38 * mm),
        Paragraph("SISTEMA CVM", estilos["marca"]),
        Paragraph(
            "Relatório Financeiro<br/>Profissional",
            estilos["titulo_capa"],
        ),
        Paragraph(
            escape(str(identificacao["DENOM_CIA"])),
            estilos["empresa"],
        ),
        Paragraph(
            "Modalidade " + ROTULOS_MODALIDADE[modalidade_normalizada],
            estilos["modalidade"],
        ),
    ]

    dados_identificacao = [
        ["Período", periodo_texto, "Layout CVM", identificacao["LAYOUT"]],
        ["CD_CVM", identificacao["CD_CVM"], "Validação", metadados["STATUS_VALIDACAO"]],
        ["Fonte", identificacao["FONTE"], "Data de geração", identificacao["DATA_GERACAO"]],
    ]
    tabela = Table(
        dados_identificacao,
        colWidths=[30 * mm, 48 * mm, 32 * mm, 55 * mm],
        rowHeights=9 * mm,
    )
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CINZA_FUNDO),
                ("GRID", (0, 0), (-1, -1), 0.5, CINZA_BORDA),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#172033")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    historia.extend(
        [
            tabela,
            PageBreak(),
            Paragraph("Resumo executivo", estilos["titulo"]),
            Paragraph(escape(resumo), estilos["corpo"]),
        ]
    )
    _adicionar_demonstracoes(historia, contexto, estilos)
    _adicionar_indicadores(
        historia,
        contexto["INDICADORES"],
        identificacao["LAYOUT"],
        anos,
        estilos,
    )

    documento.build(
        historia,
        onFirstPage=lambda canvas, doc: _configurar_metadados(
            canvas,
            doc,
            metadados,
        ),
        onLaterPages=lambda canvas, doc: _pagina_interna(
            canvas,
            doc,
            metadados,
        ),
    )

    conteudo = memoria.getvalue()
    memoria.close()

    nome_arquivo = (
        "Sistema-CVM-"
        + _nome_seguro(identificacao["DENOM_CIA"])
        + f"-{periodo_texto}-"
        + _nome_seguro(modalidade_normalizada).lower()
        + ".pdf"
    )

    return {
        "conteudo": conteudo,
        "nome_arquivo": nome_arquivo,
        "mime": MIME_PDF,
        "metadados": metadados,
    }


__all__ = [
    "MIME_PDF",
    "PeriodoInsuficientePDF",
    "gerar_pdf_financeiro",
]

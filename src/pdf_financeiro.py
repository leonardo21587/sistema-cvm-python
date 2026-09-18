from __future__ import annotations

from html import escape
from io import BytesIO
import re
import unicodedata
from typing import Any, Mapping

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
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
    }


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
    """Gera o PDF mínimo da C.2 sem recalcular dados financeiros."""
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

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Iterable, Mapping


VERSAO_CONTRATO = "1.0"

LAYOUTS_SUPORTADOS = {
    "PADRAO",
    "FINANCEIRA",
}

MODALIDADES_SUPORTADAS = {
    "EXECUTIVO_ANALISTA",
    "ACADEMICO",
}

STATUS_SUPORTADOS = {
    "OK",
    "INFO",
    "ALERTA",
    "BLOQUEIO",
}


class ErroContextoRelatorio(ValueError):
    """Contexto incompatível com o contrato do relatório."""


def _normalizar_modalidade(modalidade: str) -> str:
    valor = str(modalidade).strip().upper().replace(" ", "_")
    valor = valor.replace("/", "_")

    if valor not in MODALIDADES_SUPORTADAS:
        raise ErroContextoRelatorio(
            "Modalidade deve ser EXECUTIVO_ANALISTA ou ACADEMICO."
        )

    return valor


def _montar_periodo(anos: Iterable[int]) -> dict[str, Any]:
    anos_usados = sorted({int(ano) for ano in anos})

    if not 1 <= len(anos_usados) <= 3:
        raise ErroContextoRelatorio(
            "O contexto deve conter entre um e três exercícios."
        )

    quantidade = len(anos_usados)
    modo_temporal = {
        1: "PERIODO_INSUFICIENTE",
        2: "COMPARATIVO",
        3: "TRAJETORIA",
    }[quantidade]

    return {
        "ANOS_USADOS": anos_usados,
        "QTD_EXERCICIOS": quantidade,
        "ANO_BASE": anos_usados[0],
        "INTERMEDIARIO": (
            anos_usados[1]
            if quantidade == 3
            else None
        ),
        "RECENTE": anos_usados[-1],
        "MODO_TEMPORAL": modo_temporal,
    }


def validar_contexto_relatorio(contexto: Mapping[str, Any]) -> None:
    if not isinstance(contexto, Mapping):
        raise ErroContextoRelatorio("O contexto deve ser um mapeamento.")

    blocos = {
        "VERSAO_CONTRATO",
        "IDENTIFICACAO",
        "PERIODO",
        "DEMONSTRACOES",
        "INDICADORES",
        "NARRATIVA",
        "VALIDACAO",
        "METODOLOGIA",
        "FONTES",
        "FIGURAS",
        "EXTENSOES",
    }
    faltantes = blocos.difference(contexto)

    if faltantes:
        raise ErroContextoRelatorio(
            "Blocos ausentes no contexto: "
            + ", ".join(sorted(faltantes))
        )

    if contexto["VERSAO_CONTRATO"] != VERSAO_CONTRATO:
        raise ErroContextoRelatorio("Versão de contrato não suportada.")

    identificacao = contexto["IDENTIFICACAO"]
    if not isinstance(identificacao, Mapping):
        raise ErroContextoRelatorio("IDENTIFICACAO deve ser um mapeamento.")

    for campo in ("DENOM_CIA", "CD_CVM", "LAYOUT", "MODALIDADE"):
        if not identificacao.get(campo):
            raise ErroContextoRelatorio(
                f"Campo obrigatório ausente em IDENTIFICACAO: {campo}."
            )

    if identificacao["LAYOUT"] not in LAYOUTS_SUPORTADOS:
        raise ErroContextoRelatorio("Layout deve ser PADRAO ou FINANCEIRA.")

    if (
        identificacao["MODALIDADE"]
        != _normalizar_modalidade(identificacao["MODALIDADE"])
    ):
        raise ErroContextoRelatorio("MODALIDADE não está normalizada.")

    periodo = contexto["PERIODO"]
    if not isinstance(periodo, Mapping):
        raise ErroContextoRelatorio("PERIODO deve ser um mapeamento.")

    periodo_esperado = _montar_periodo(periodo.get("ANOS_USADOS", []))
    if dict(periodo) != periodo_esperado:
        raise ErroContextoRelatorio("Bloco PERIODO inconsistente.")

    demonstracoes = contexto["DEMONSTRACOES"]
    if (
        not isinstance(demonstracoes, Mapping)
        or not {"BPA", "BPP", "DRE"}.issubset(demonstracoes)
    ):
        raise ErroContextoRelatorio(
            "DEMONSTRACOES deve conter BPA, BPP e DRE."
        )

    indicadores = contexto["INDICADORES"]
    if (
        not isinstance(indicadores, Mapping)
        or not {"ANALISE", "BASE_OFICIAL"}.issubset(indicadores)
    ):
        raise ErroContextoRelatorio(
            "INDICADORES deve conter ANALISE e BASE_OFICIAL."
        )

    validacao = contexto["VALIDACAO"]
    if not isinstance(validacao, Mapping):
        raise ErroContextoRelatorio("VALIDACAO deve ser um mapeamento.")

    status = str(validacao.get("STATUS_GERAL", "")).strip().upper()
    if status not in STATUS_SUPORTADOS:
        raise ErroContextoRelatorio("STATUS_GERAL de validação inválido.")

    if "TABELA" not in validacao:
        raise ErroContextoRelatorio("VALIDACAO deve conter TABELA.")

    if not isinstance(contexto["FIGURAS"], Mapping):
        raise ErroContextoRelatorio("FIGURAS deve ser um mapeamento.")

    if not isinstance(contexto["EXTENSOES"], Mapping):
        raise ErroContextoRelatorio("EXTENSOES deve ser um mapeamento.")


def montar_contexto_relatorio(
    *,
    identificacao: Mapping[str, Any],
    anos: Iterable[int],
    demonstracoes: Mapping[str, Any],
    indicadores: Mapping[str, Any],
    narrativa: Any,
    status_validacao: str,
    validacao: Any,
    metodologia: Any,
    fontes: Any,
    modalidade: str = "EXECUTIVO_ANALISTA",
    figuras: Mapping[str, Any] | None = None,
    extensoes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Monta o payload sem consultar fontes ou recalcular resultados."""
    modalidade_normalizada = _normalizar_modalidade(modalidade)
    layout = str(
        identificacao.get(
            "LAYOUT",
            identificacao.get("LAYOUT_CVM", ""),
        )
    ).strip().upper()

    identificacao_contexto = {
        "DENOM_CIA": str(identificacao.get("DENOM_CIA", "")).strip(),
        "CD_CVM": str(identificacao.get("CD_CVM", "")).strip(),
        "CNPJ": identificacao.get(
            "CNPJ",
            identificacao.get("CNPJ_CIA"),
        ),
        "LAYOUT": layout,
        "FONTE": identificacao.get("FONTE", "DFP consolidadas / CVM"),
        "MODALIDADE": modalidade_normalizada,
        "DATA_GERACAO": identificacao.get(
            "DATA_GERACAO",
            date.today().isoformat(),
        ),
    }

    contexto = {
        "VERSAO_CONTRATO": VERSAO_CONTRATO,
        "IDENTIFICACAO": identificacao_contexto,
        "PERIODO": _montar_periodo(anos),
        "DEMONSTRACOES": deepcopy(dict(demonstracoes)),
        "INDICADORES": deepcopy(dict(indicadores)),
        "NARRATIVA": deepcopy(narrativa),
        "VALIDACAO": {
            "STATUS_GERAL": str(status_validacao).strip().upper(),
            "TABELA": deepcopy(validacao),
        },
        "METODOLOGIA": deepcopy(metodologia),
        "FONTES": deepcopy(fontes),
        "FIGURAS": deepcopy(dict(figuras or {})),
        "EXTENSOES": deepcopy(dict(extensoes or {})),
    }

    validar_contexto_relatorio(contexto)
    return contexto


__all__ = [
    "ErroContextoRelatorio",
    "MODALIDADES_SUPORTADAS",
    "VERSAO_CONTRATO",
    "montar_contexto_relatorio",
    "validar_contexto_relatorio",
]

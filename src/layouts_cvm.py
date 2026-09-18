from __future__ import annotations

from dataclasses import dataclass
import unicodedata

import pandas as pd


LAYOUT_PADRAO = "PADRAO"
LAYOUT_FINANCEIRA = "FINANCEIRA"
LAYOUT_SEGUROS_ESPECIAL = "SEGUROS_ESPECIAL"
LAYOUT_OUTRO = "OUTRO"


INDICADORES_TODOS = {
    "IPL",
    "PCT",
    "CE",
    "EFSAT",
    "LG",
    "LC",
    "LS",
    "ICJ",
    "GA",
    "RSV",
    "ROA",
    "ROE",
}

# Para layouts financeiros e securitários especiais, o modelo tradicional
# do trabalho não deve reutilizar mecanicamente contas que têm outro sentido
# econômico. ROA e ROE continuam apoiados em Ativo Total, Resultado Líquido
# Consolidado e Patrimônio Líquido Consolidado.
INDICADORES_APLICAVEIS_ESPECIAIS = {
    "ROA",
    "ROE",
}


@dataclass(frozen=True)
class LayoutCVM:
    codigo: str
    descricao: str
    codigo_pl: str | None
    codigo_ll: str | None
    aplicaveis: frozenset[str]

    @property
    def especial(self) -> bool:
        return self.codigo != LAYOUT_PADRAO


def normalizar_descricao(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""

    texto = unicodedata.normalize(
        "NFKD",
        str(valor),
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(
            caractere
        )
    )

    return " ".join(
        texto.upper().split()
    )


def _resolver_codigo_por_descricao_exata(
    df: pd.DataFrame,
    descricoes: set[str],
) -> str | None:
    if df is None or df.empty:
        return None

    obrigatorias = {
        "CD_CONTA",
        "DS_CONTA",
    }

    if not obrigatorias.issubset(
        set(df.columns)
    ):
        return None

    descricoes_norm = {
        normalizar_descricao(
            descricao
        )
        for descricao in descricoes
    }

    d = df[
        [
            "CD_CONTA",
            "DS_CONTA",
        ]
    ].copy()

    d["_DS_NORM"] = (
        d["DS_CONTA"]
        .map(
            normalizar_descricao
        )
    )

    d = d[
        d["_DS_NORM"].isin(
            descricoes_norm
        )
    ].copy()

    if d.empty:
        return None

    d["CD_CONTA"] = (
        d["CD_CONTA"]
        .astype(str)
        .str.strip()
    )

    # Se por alguma razão houver mais de uma conta com exatamente a mesma
    # descrição, priorizamos a conta estrutural mais curta / menos profunda.
    d["_PROFUNDIDADE"] = (
        d["CD_CONTA"]
        .str.count(r"\.")
    )

    d["_TAMANHO"] = (
        d["CD_CONTA"]
        .str.len()
    )

    d = (
        d.sort_values(
            [
                "_PROFUNDIDADE",
                "_TAMANHO",
                "CD_CONTA",
            ]
        )
        .drop_duplicates(
            subset=[
                "CD_CONTA",
            ]
        )
    )

    return str(
        d.iloc[0][
            "CD_CONTA"
        ]
    )


def resolver_codigo_pl(
    bpp: pd.DataFrame,
) -> str | None:
    return _resolver_codigo_por_descricao_exata(
        bpp,
        {
            "Patrimônio Líquido Consolidado",
        },
    )


def resolver_codigo_ll(
    dre: pd.DataFrame,
) -> str | None:
    return _resolver_codigo_por_descricao_exata(
        dre,
        {
            "Lucro/Prejuízo Consolidado do Período",
            "Lucro ou Prejuízo Líquido Consolidado do Período",
        },
    )


def detectar_layout(
    bpp: pd.DataFrame,
    dre: pd.DataFrame,
) -> LayoutCVM:
    codigo_pl = resolver_codigo_pl(
        bpp
    )

    codigo_ll = resolver_codigo_ll(
        dre
    )

    if (
        codigo_pl == "2.03"
        and codigo_ll == "3.11"
    ):
        return LayoutCVM(
            codigo=LAYOUT_PADRAO,
            descricao=(
                "Empresa comercial, industrial "
                "ou outro layout padrão"
            ),
            codigo_pl=codigo_pl,
            codigo_ll=codigo_ll,
            aplicaveis=frozenset(
                INDICADORES_TODOS
            ),
        )

    if codigo_pl in {
        "2.07",
        "2.08",
    }:
        return LayoutCVM(
            codigo=LAYOUT_FINANCEIRA,
            descricao=(
                "Instituição financeira / "
                "layout bancário"
            ),
            codigo_pl=codigo_pl,
            codigo_ll=codigo_ll,
            aplicaveis=frozenset(
                INDICADORES_APLICAVEIS_ESPECIAIS
            ),
        )

    if (
        codigo_pl == "2.03"
        and codigo_ll == "3.13"
    ):
        return LayoutCVM(
            codigo=LAYOUT_SEGUROS_ESPECIAL,
            descricao=(
                "Layout securitário especial"
            ),
            codigo_pl=codigo_pl,
            codigo_ll=codigo_ll,
            aplicaveis=frozenset(
                INDICADORES_APLICAVEIS_ESPECIAIS
            ),
        )

    return LayoutCVM(
        codigo=LAYOUT_OUTRO,
        descricao=(
            "Layout não reconhecido automaticamente"
        ),
        codigo_pl=codigo_pl,
        codigo_ll=codigo_ll,
        aplicaveis=frozenset(),
    )


def indicador_aplicavel(
    layout: LayoutCVM,
    indicador: str,
) -> bool:
    return (
        str(
            indicador
        )
        .upper()
        .strip()
        in layout.aplicaveis
    )


def motivo_nao_aplicavel(
    layout: LayoutCVM,
    indicador: str,
) -> str | None:
    indicador = (
        str(
            indicador
        )
        .upper()
        .strip()
    )

    if indicador_aplicavel(
        layout,
        indicador,
    ):
        return None

    if layout.codigo == LAYOUT_FINANCEIRA:
        return (
            "N/A — instituição financeira: "
            "o indicador depende da estrutura contábil "
            "tradicional de companhias não financeiras."
        )

    if layout.codigo == LAYOUT_SEGUROS_ESPECIAL:
        return (
            "N/A — layout securitário especial: "
            "o indicador não é calculado automaticamente "
            "com a metodologia tradicional do trabalho."
        )

    return (
        "N/A — layout contábil não reconhecido "
        "automaticamente."
    )

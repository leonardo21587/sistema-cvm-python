from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.indicadores import (
    PERCENTUAIS,
    quadro_indicadores,
)


# ============================================================
# METADADOS
# ============================================================

NOMES = {
    "IPL": "Imobilização do Patrimônio Líquido",
    "PCT": "Participação de Capital de Terceiros",
    "CE": "Composição do Endividamento",
    "EFSAT": "Endividamento Financeiro sobre Ativo Total",
    "LG": "Liquidez Geral",
    "LC": "Liquidez Corrente",
    "LS": "Liquidez Seca",
    "ICJ": "Índice de Cobertura de Juros",
    "GA": "Giro do Ativo",
    "RSV": "Retorno sobre Vendas",
    "ROA": "Retorno sobre o Ativo",
    "ROE": "Retorno sobre o Patrimônio Líquido",
}


ORDEM_INDICADORES = [
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
]


GRUPOS_DASHBOARD = {
    "estrutura": [
        "IPL",
        "PCT",
        "CE",
        "EFSAT",
    ],

    "liquidez": [
        "LG",
        "LC",
        "LS",
    ],

    "icj": [
        "ICJ",
    ],

    "rentabilidade": [
        "RSV",
        "ROA",
        "ROE",
    ],

    "ga": [
        "GA",
    ],
}


# ============================================================
# UTILITÁRIOS
# ============================================================

def _numero(valor):
    if valor is None or pd.isna(valor):
        return None

    try:
        return float(valor)

    except (TypeError, ValueError):
        return None


def _linha_indicador(
    quadro: pd.DataFrame,
    codigo: str,
):
    linhas = quadro.loc[
        quadro["INDICADOR"]
        .astype(str)
        .eq(codigo)
    ]

    if linhas.empty:
        return None

    if len(linhas) != 1:
        raise RuntimeError(
            "Indicador duplicado no quadro: "
            f"{codigo}"
        )

    return linhas.iloc[0]


def _valor_ano(
    quadro: pd.DataFrame,
    codigo: str,
    ano: int,
):
    linha = _linha_indicador(
        quadro,
        codigo,
    )

    if linha is None:
        return None

    if ano not in linha.index:
        return None

    return _numero(
        linha[ano]
    )


def _anos_validos(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None,
) -> list[int]:
    colunas_anos = sorted(
        int(coluna)
        for coluna in quadro.columns
        if isinstance(coluna, int)
    )

    if anos is None:
        return colunas_anos

    solicitados = sorted(
        int(ano)
        for ano in anos
    )

    return [
        ano
        for ano in solicitados
        if ano in colunas_anos
    ]


# ============================================================
# FORMATAÇÃO
# ============================================================

def formatar_valor_dashboard(
    codigo: str,
    valor,
) -> str:
    valor = _numero(valor)

    if valor is None:
        return "N/D"

    if codigo in PERCENTUAIS:
        numero = (
            f"{valor * 100:.2f}"
            .replace(".", ",")
        )

        return f"{numero}%"

    numero = (
        f"{valor:.2f}"
        .replace(".", ",")
    )

    if codigo in {
        "GA",
        "ICJ",
    }:
        return f"{numero}x"

    return numero


def formatar_delta_dashboard(
    codigo: str,
    base,
    recente,
) -> str:
    base = _numero(base)
    recente = _numero(recente)

    if (
        base is None
        or recente is None
    ):
        return "N/D"

    delta = recente - base

    sinal = (
        "+"
        if delta > 0
        else ""
    )

    if codigo in PERCENTUAIS:
        numero = (
            f"{delta * 100:.2f}"
            .replace(".", ",")
        )

        return (
            f"{sinal}{numero} p.p."
        )

    numero = (
        f"{delta:.2f}"
        .replace(".", ",")
    )

    if codigo in {
        "GA",
        "ICJ",
    }:
        return (
            f"{sinal}{numero}x"
        )

    return (
        f"{sinal}{numero}"
    )


# ============================================================
# SÉRIE DE UM INDICADOR
# ============================================================

def serie_indicador(
    quadro: pd.DataFrame,
    codigo: str,
    anos: list[int] | tuple[int, ...] | None = None,
) -> pd.DataFrame:
    codigo = str(
        codigo
    ).strip().upper()

    if codigo not in NOMES:
        raise ValueError(
            f"Indicador inválido: {codigo}"
        )

    anos_usados = _anos_validos(
        quadro,
        anos,
    )

    registros = []

    for ano in anos_usados:
        valor = _valor_ano(
            quadro,
            codigo,
            ano,
        )

        registros.append(
            {
                "ANO": ano,
                "INDICADOR": codigo,
                "NOME": NOMES[codigo],
                "VALOR": valor,
            }
        )

    return pd.DataFrame(
        registros
    )


# ============================================================
# DADOS DOS CARDS
# ============================================================

def montar_cards_dashboard(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None = None,
) -> pd.DataFrame:
    anos_usados = _anos_validos(
        quadro,
        anos,
    )

    if not anos_usados:
        return pd.DataFrame()

    ano_base = min(
        anos_usados
    )

    ano_recente = max(
        anos_usados
    )

    registros = []

    for codigo in ORDEM_INDICADORES:
        linha = _linha_indicador(
            quadro,
            codigo,
        )

        if linha is None:
            continue

        base = _valor_ano(
            quadro,
            codigo,
            ano_base,
        )

        recente = _valor_ano(
            quadro,
            codigo,
            ano_recente,
        )

        registros.append(
            {
                "INDICADOR": codigo,
                "NOME": NOMES[codigo],
                "ANO_BASE": ano_base,
                "ANO_RECENTE": ano_recente,
                "VALOR_BASE": base,
                "VALOR_RECENTE": recente,
                "VALOR_RECENTE_FMT": (
                    formatar_valor_dashboard(
                        codigo,
                        recente,
                    )
                ),
                "DELTA_BASE_RECENTE": (
                    None
                    if (
                        base is None
                        or recente is None
                    )
                    else recente - base
                ),
                "DELTA_FMT": (
                    formatar_delta_dashboard(
                        codigo,
                        base,
                        recente,
                    )
                ),
            }
        )

    return pd.DataFrame(
        registros
    )


# ============================================================
# PREPARAÇÃO DE DADOS PARA GRÁFICOS
# ============================================================

def preparar_series_grafico(
    quadro: pd.DataFrame,
    codigos: list[str],
    anos: list[int] | tuple[int, ...] | None = None,
) -> pd.DataFrame:
    anos_usados = _anos_validos(
        quadro,
        anos,
    )

    registros = []

    for codigo in codigos:
        codigo = str(
            codigo
        ).strip().upper()

        if codigo not in NOMES:
            raise ValueError(
                f"Indicador inválido: {codigo}"
            )

        for ano in anos_usados:
            valor = _valor_ano(
                quadro,
                codigo,
                ano,
            )

            if valor is None:
                valor_grafico = None

            elif codigo in PERCENTUAIS:
                valor_grafico = (
                    valor * 100
                )

            else:
                valor_grafico = valor

            registros.append(
                {
                    "ANO": ano,
                    "INDICADOR": codigo,
                    "NOME": NOMES[codigo],
                    "VALOR_ORIGINAL": valor,
                    "VALOR_GRAFICO": valor_grafico,
                }
            )

    return pd.DataFrame(
        registros
    )


# ============================================================
# GRÁFICO GENÉRICO
# ============================================================

def grafico_linhas(
    quadro: pd.DataFrame,
    codigos: list[str],
    anos: list[int] | tuple[int, ...] | None,
    titulo: str,
    eixo_y: str,
    percentual: bool = False,
    mostrar_legenda: bool = True,
) -> go.Figure:
    dados = preparar_series_grafico(
        quadro,
        codigos,
        anos,
    )

    fig = go.Figure()

    anos_usados = _anos_validos(
        quadro,
        anos,
    )

    for codigo in codigos:
        parte = dados.loc[
            dados["INDICADOR"]
            == codigo
        ].sort_values(
            "ANO"
        )

        if parte.empty:
            continue

        x = [
            str(ano)
            for ano in parte["ANO"]
        ]

        y = parte[
            "VALOR_GRAFICO"
        ].tolist()

        if percentual:
            hover = (
                "<b>%{fullData.name}</b><br>"
                "Ano: %{x}<br>"
                "Valor: %{y:.2f}%"
                "<extra></extra>"
            )

        else:
            hover = (
                "<b>%{fullData.name}</b><br>"
                "Ano: %{x}<br>"
                "Valor: %{y:.2f}"
                "<extra></extra>"
            )

        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                name=codigo,
                customdata=[
                    NOMES[codigo]
                    for _ in x
                ],
                hovertemplate=hover,
                connectgaps=False,
            )
        )

    fig.update_layout(
        title={
            "text": titulo,
            "x": 0,
            "xanchor": "left",
        },
        template="plotly_white",
        height=390,
        margin={
            "l": 40,
            "r": 20,
            "t": 65,
            "b": 45,
        },
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
        showlegend=mostrar_legenda,
        xaxis={
            "title": "",
            "type": "category",
            "categoryorder": "array",
            "categoryarray": [
                str(ano)
                for ano in anos_usados
            ],
            "showgrid": False,
        },
        yaxis={
            "title": eixo_y,
            "rangemode": "tozero",
        },
    )

    if percentual:
        fig.update_yaxes(
            ticksuffix="%",
        )

    return fig


# ============================================================
# GRÁFICOS ESPECÍFICOS DO DASHBOARD
# ============================================================

def grafico_estrutura_capital(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None = None,
) -> go.Figure:
    return grafico_linhas(
        quadro=quadro,
        codigos=GRUPOS_DASHBOARD[
            "estrutura"
        ],
        anos=anos,
        titulo=(
            "Estrutura de Capital"
        ),
        eixo_y="Percentual",
        percentual=True,
        mostrar_legenda=True,
    )


def grafico_liquidez(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None = None,
) -> go.Figure:
    return grafico_linhas(
        quadro=quadro,
        codigos=GRUPOS_DASHBOARD[
            "liquidez"
        ],
        anos=anos,
        titulo="Liquidez",
        eixo_y="Razão",
        percentual=False,
        mostrar_legenda=True,
    )


def grafico_icj(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None = None,
) -> go.Figure:
    return grafico_linhas(
        quadro=quadro,
        codigos=GRUPOS_DASHBOARD[
            "icj"
        ],
        anos=anos,
        titulo=(
            "Índice de Cobertura de Juros"
        ),
        eixo_y="Vezes",
        percentual=False,
        mostrar_legenda=False,
    )


def grafico_rentabilidade(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None = None,
) -> go.Figure:
    return grafico_linhas(
        quadro=quadro,
        codigos=GRUPOS_DASHBOARD[
            "rentabilidade"
        ],
        anos=anos,
        titulo=(
            "Rentabilidade"
        ),
        eixo_y="Percentual",
        percentual=True,
        mostrar_legenda=True,
    )


def grafico_giro_ativo(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None = None,
) -> go.Figure:
    return grafico_linhas(
        quadro=quadro,
        codigos=GRUPOS_DASHBOARD[
            "ga"
        ],
        anos=anos,
        titulo="Giro do Ativo",
        eixo_y="Vezes",
        percentual=False,
        mostrar_legenda=False,
    )


# ============================================================
# PACOTE COMPLETO PARA O DASHBOARD
# ============================================================

def montar_graficos_dashboard(
    quadro: pd.DataFrame,
    anos: list[int] | tuple[int, ...] | None = None,
) -> dict[str, go.Figure]:
    return {
        "estrutura": (
            grafico_estrutura_capital(
                quadro,
                anos,
            )
        ),

        "liquidez": (
            grafico_liquidez(
                quadro,
                anos,
            )
        ),

        "icj": (
            grafico_icj(
                quadro,
                anos,
            )
        ),

        "rentabilidade": (
            grafico_rentabilidade(
                quadro,
                anos,
            )
        ),

        "ga": (
            grafico_giro_ativo(
                quadro,
                anos,
            )
        ),
    }


# ============================================================
# TESTE
# ============================================================

def main():
    cd_cvm = "004170"

    anos = [
        2023,
        2024,
        2025,
    ]

    print(
        "=" * 78
    )

    print(
        "SISTEMA CVM — TESTE DOS GRÁFICOS"
    )

    print(
        "=" * 78
    )

    quadro = quadro_indicadores(
        cd_cvm,
        anos=anos,
    )

    if quadro.empty:
        print(
            "ERRO: quadro de indicadores vazio."
        )
        return

    cards = montar_cards_dashboard(
        quadro,
        anos,
    )

    print()
    print(
        "CARDS DO DASHBOARD"
    )

    print(
        "-" * 78
    )

    print(
        cards[
            [
                "INDICADOR",
                "VALOR_RECENTE_FMT",
                "DELTA_FMT",
            ]
        ].to_string(
            index=False
        )
    )

    graficos = montar_graficos_dashboard(
        quadro,
        anos,
    )

    print()
    print(
        "GRÁFICOS GERADOS"
    )

    print(
        "-" * 78
    )

    for nome, figura in (
        graficos.items()
    ):
        print(
            f"{nome}: "
            f"{len(figura.data)} "
            f"série(s)"
        )

    total_series = sum(
        len(figura.data)
        for figura
        in graficos.values()
    )

    print()
    print(
        f"TOTAL DE INDICADORES "
        f"REPRESENTADOS: "
        f"{total_series}"
    )

    esperado = 12

    if total_series == esperado:
        print(
            "STATUS: OK"
        )

    else:
        print(
            "STATUS: VERIFICAR"
        )

    print()
    print(
        "OBSERVAÇÃO:"
    )

    print(
        "Os gráficos não recalculam indicadores. "
        "Eles utilizam quadro_indicadores() "
        "como fonte oficial."
    )


if __name__ == "__main__":
    main()
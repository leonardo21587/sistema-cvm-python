from pathlib import Path
import html
import re
import unicodedata

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.demonstracoes import (
    montar_quadro_demonstracao,
    resumo_empresa,
)

from src.padronizacao import (
    montar_demonstracao_padronizada,
)

from src.indicadores import (
    quadro_indicadores,
    detalhar_indicador,
    validar_dupont,
)

from src.relatorio import (
    gerar_relatorio,
)

from src.graficos import (
    montar_cards_dashboard,
    montar_graficos_dashboard,
)

from src.validacao import (
    validar_empresa,
)

from src.exportacao import (
    gerar_excel_sistema,
    nome_arquivo_exportacao,
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Sistema CVM - Análise Financeira",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent

ARQUIVO_EMPRESAS = (
    BASE_DIR
    / "data"
    / "processed"
    / "empresas.parquet"
)


# ============================================================
# INDICADORES — METADADOS
# ============================================================

NOMES_INDICADORES = {
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


LEITURAS_INDICADORES = {
    "IPL": (
        "Parcela do PL aplicada em investimentos, "
        "imobilizado e intangível."
    ),

    "PCT": (
        "Capital de terceiros em relação ao PL; "
        "leitura contextual."
    ),

    "CE": (
        "Parcela de curto prazo do capital de terceiros; "
        "leitura contextual."
    ),

    "EFSAT": (
        "Dívida financeira em relação ao ativo; "
        "leitura contextual."
    ),

    "LG": (
        "Ativos realizáveis em relação "
        "às obrigações totais."
    ),

    "LC": (
        "Ativo circulante em relação "
        "ao passivo circulante."
    ),

    "LS": (
        "Cobertura do passivo circulante pelos "
        "componentes definidos na metodologia."
    ),

    "ICJ": (
        "Cobertura da despesa financeira absoluta "
        "pelo EBIT."
    ),

    "GA": (
        "Receita gerada por unidade de ativo médio."
    ),

    "RSV": (
        "Resultado líquido em relação "
        "à receita líquida."
    ),

    "ROA": (
        "Resultado líquido em relação "
        "ao ativo médio."
    ),

    "ROE": (
        "Resultado líquido em relação "
        "ao PL médio ajustado."
    ),
}


PERCENTUAIS_INDICADORES = {
    "IPL",
    "PCT",
    "CE",
    "EFSAT",
    "RSV",
    "ROA",
    "ROE",
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


COMPONENTES_INDICADORES = {
    "IPL": [
        "INV",
        "IMOB",
        "INTANG",
        "AP",
        "PL",
    ],

    "PCT": [
        "PC",
        "PNC",
        "CT",
        "PL",
    ],

    "CE": [
        "PC",
        "PNC",
        "CT",
    ],

    "EFSAT": [
        "EMP_CP",
        "EMP_LP",
        "PF",
        "AT",
    ],

    "LG": [
        "AC",
        "RLP",
        "PC",
        "PNC",
        "CT",
    ],

    "LC": [
        "AC",
        "PC",
    ],

    "LS": [
        "DISP",
        "APLIC",
        "CR",
        "PC",
    ],

    "ICJ": [
        "EBIT",
        "DESP_FIN",
    ],

    "GA": [
        "RECEITA",
        "AT_inicial",
        "AT",
        "ATm",
    ],

    "RSV": [
        "LL",
        "RECEITA",
    ],

    "ROA": [
        "LL",
        "AT_inicial",
        "AT",
        "ATm",
    ],

    "ROE": [
        "LL",
        "PL_inicial",
        "PL",
        "PLma",
    ],
}


ROTULOS_COMPONENTES = {
    "AT": "Ativo Total final",
    "AC": "Ativo Circulante",
    "DISP": "Disponível",
    "APLIC": "Aplicações Financeiras",
    "CR": "Contas a Receber",
    "RLP": "Realizável a Longo Prazo",
    "INV": "Investimentos",
    "IMOB": "Imobilizado",
    "INTANG": "Intangível",
    "PC": "Passivo Circulante",
    "EMP_CP": "Empréstimos CP",
    "PNC": "Passivo Não Circulante",
    "EMP_LP": "Empréstimos LP",
    "PL": "Patrimônio Líquido final",
    "RECEITA": "Receita Líquida",
    "EBIT": "EBIT",
    "DESP_FIN": "Despesas Financeiras",
    "LL": "Resultado Líquido",
    "AP": "Ativo Permanente",
    "CT": "Capital de Terceiros",
    "PF": "Passivo Financeiro",
    "ATm": "Ativo Médio",
    "PLma": "PL Médio Ajustado",
    "AT_inicial": "Ativo Total inicial",
    "PL_inicial": "Patrimônio Líquido inicial",
}


# ============================================================
# TEXTO
# ============================================================

def normalizar_texto(texto):

    if pd.isna(texto):
        return ""

    texto = str(texto)

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(
            caractere
        )
    )

    texto = texto.upper().strip()

    return re.sub(
        r"\s+",
        " ",
        texto,
    )


def formatar_cnpj(cnpj):

    if pd.isna(cnpj):
        return "N/D"

    cnpj = re.sub(
        r"\D",
        "",
        str(cnpj),
    )

    if len(cnpj) != 14:
        return cnpj

    return (
        f"{cnpj[:2]}."
        f"{cnpj[2:5]}."
        f"{cnpj[5:8]}/"
        f"{cnpj[8:12]}-"
        f"{cnpj[12:]}"
    )


# ============================================================
# FORMATAÇÃO
# ============================================================

def formatar_va(valor):

    if pd.isna(valor):
        return "N/D"

    try:
        valor = float(valor)

    except (TypeError, ValueError):
        return "N/D"

    if valor == 0:
        return "0"

    texto = f"{abs(valor):,.0f}"

    texto = (
        texto
        .replace(",", "TEMP")
        .replace(".", ",")
        .replace("TEMP", ".")
    )

    if valor < 0:
        return f"({texto})"

    return texto


def formatar_av(valor):

    if pd.isna(valor):
        return "N/D"

    return (
        f"{float(valor):.2f}%"
        .replace(".", ",")
    )


def formatar_ah(valor):

    if pd.isna(valor):
        return "N/D"

    return (
        f"{float(valor):.2f}"
        .replace(".", ",")
    )


def formatar_indicador(
    indicador,
    valor,
):

    if valor is None or pd.isna(valor):
        return "N/D"

    valor = float(valor)

    if indicador in PERCENTUAIS_INDICADORES:

        return (
            f"{valor * 100:.2f}%"
            .replace(".", ",")
        )

    return (
        f"{valor:.2f}"
        .replace(".", ",")
    )


def formatar_raw(valor):

    if pd.isna(valor):
        return "N/D"

    try:
        return formatar_va(
            float(valor)
        )

    except (TypeError, ValueError):
        return str(valor)


# ============================================================
# CATÁLOGO
# ============================================================

@st.cache_data(show_spinner=False)
def carregar_empresas():

    if not ARQUIVO_EMPRESAS.exists():

        raise FileNotFoundError(
            f"Arquivo não encontrado: "
            f"{ARQUIVO_EMPRESAS}"
        )

    df = pd.read_parquet(
        ARQUIVO_EMPRESAS
    )

    obrigatorias = [
        "CD_CVM",
        "CNPJ_CIA",
        "DENOM_CIA",
    ]

    ausentes = [
        coluna
        for coluna in obrigatorias
        if coluna not in df.columns
    ]

    if ausentes:

        raise ValueError(
            "Colunas obrigatórias ausentes: "
            + ", ".join(
                ausentes
            )
        )

    df = df.copy()

    df["CD_CVM"] = (
        df["CD_CVM"]
        .astype("string")
        .str.strip()
        .str.zfill(6)
    )

    df["CNPJ_CIA"] = (
        df["CNPJ_CIA"]
        .astype("string")
        .str.replace(
            r"\D",
            "",
            regex=True,
        )
        .str.zfill(14)
    )

    df["DENOM_CIA"] = (
        df["DENOM_CIA"]
        .astype("string")
        .str.strip()
    )

    df["_PESQUISA"] = (
        df["DENOM_CIA"]
        .fillna("")
        .map(
            normalizar_texto
        )
    )

    return (
        df
        .sort_values(
            [
                "DENOM_CIA",
                "CD_CVM",
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
    )


def pesquisar_empresas(
    df,
    termo,
):

    termo = str(
        termo
    ).strip()

    if not termo:

        return (
            df
            .iloc[0:0]
            .copy()
        )

    nome = normalizar_texto(
        termo
    )

    numerico = re.sub(
        r"\D",
        "",
        termo,
    )

    mascara = (
        df["_PESQUISA"]
        .str.contains(
            nome,
            regex=False,
            na=False,
        )
    )

    if numerico:

        mascara = (
            mascara
            | df["CD_CVM"]
            .str.contains(
                numerico,
                regex=False,
                na=False,
            )
            | df["CNPJ_CIA"]
            .str.contains(
                numerico,
                regex=False,
                na=False,
            )
        )

    return (
        df.loc[
            mascara
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )


# ============================================================
# CACHE
# ============================================================

@st.cache_data(show_spinner=False)
def carregar_resumo_empresa(
    cd_cvm,
):

    return resumo_empresa(
        cd_cvm
    )


@st.cache_data(show_spinner=False)
def carregar_padronizada(
    cd_cvm,
    demonstracao,
    anos_tuple,
):

    return montar_demonstracao_padronizada(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=list(
            anos_tuple
        ),
    )


@st.cache_data(show_spinner=False)
def carregar_raw(
    cd_cvm,
    demonstracao,
    anos_tuple,
):

    return montar_quadro_demonstracao(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=list(
            anos_tuple
        ),
        somente_contas_fixas=False,
    )


@st.cache_data(show_spinner=False)
def carregar_indicadores(
    cd_cvm,
    anos_tuple,
):

    return quadro_indicadores(
        cd_cvm,
        anos=list(
            anos_tuple
        ),
    )


@st.cache_data(show_spinner=False)
def carregar_detalhe_indicador(
    cd_cvm,
    ano,
    indicador,
):

    return detalhar_indicador(
        cd_cvm,
        ano,
        indicador,
    )


@st.cache_data(show_spinner=False)
def carregar_dupont(
    cd_cvm,
    anos_tuple,
):

    return validar_dupont(
        cd_cvm,
        anos=list(
            anos_tuple
        ),
    )


@st.cache_data(show_spinner=False)
def carregar_relatorio(
    cd_cvm,
    nome_empresa,
    anos_tuple,
):

    return gerar_relatorio(
        cd_cvm=cd_cvm,
        nome_empresa=nome_empresa,
        anos=list(
            anos_tuple
        ),
    )


@st.cache_data(show_spinner=False)
def carregar_validacao(
    cd_cvm,
    anos_tuple,
):

    return validar_empresa(
        cd_cvm=cd_cvm,
        anos=list(
            anos_tuple
        ),
    )


# ============================================================
# TABELA PADRONIZADA
# ============================================================

def linha_em_negrito(
    linha,
    tipo,
):

    if tipo == "CABECALHO":
        return True

    letras = "".join(
        caractere
        for caractere in str(
            linha
        )
        if caractere.isalpha()
    )

    return bool(
        letras
        and letras
        == letras.upper()
    )


def renderizar_tabela_padronizada(
    df,
    nome_empresa,
    titulo_primeira_coluna,
):

    if df.empty:

        st.warning(
            "Demonstração padronizada "
            "não disponível."
        )

        return

    anos = sorted(
        [
            int(
                str(
                    coluna
                ).replace(
                    "VA_",
                    "",
                )
            )
            for coluna in df.columns
            if str(
                coluna
            ).startswith(
                "VA_"
            )
        ],
        reverse=True,
    )

    ano_base = min(
        anos
    )

    total_numericas = sum(
        2
        if ano == ano_base
        else 3
        for ano in anos
    )

    partes = [
        """
        <!DOCTYPE html>

        <html
            lang="pt-BR"
            translate="no"
            class="notranslate"
        >

        <head>

        <meta charset="UTF-8">

        <style>

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            padding: 4px;
            font-family: Arial, Helvetica, sans-serif;
            background: white;
            color: #111827;
        }

        .wrapper {
            width: 100%;
            overflow-x: auto;
        }

        table {
            border-collapse: collapse;
            width: 100%;
            min-width: 1050px;
            background: white;
            font-size: 14px;
        }

        th,
        td {
            border: 1px solid #1f2937;
            padding: 6px 8px;
        }

        thead th {
            background: #365f9d;
            color: white;
            text-align: center;
            font-weight: 700;
        }

        .empresa {
            font-size: 16px;
        }

        .descricao {
            width: 330px;
            min-width: 330px;
            text-align: left;
        }

        td.numero {
            text-align: right;
            white-space: nowrap;
            min-width: 92px;
        }

        tr.negrito td.descricao,
        tr.cabecalho td.descricao {
            font-weight: 700;
        }

        tr.cabecalho td.numero {
            color: #6b7280;
            text-align: center;
        }

        tr:hover td {
            background: #f8fafc;
        }

        </style>

        </head>

        <body
            class="notranslate"
            translate="no"
        >

        <div class="wrapper">

        <table>
        """
    ]

    partes.append(
        f"""
        <thead>

        <tr>

            <th
                colspan="{1 + total_numericas}"
                class="empresa"
                translate="no"
            >
                {html.escape(str(nome_empresa))}
            </th>

        </tr>
        """
    )

    partes.append(
        "<tr>"
    )

    partes.append(
        f"""
        <th
            rowspan="2"
            class="descricao"
        >
            {html.escape(str(titulo_primeira_coluna))}
        </th>
        """
    )

    for ano in anos:

        colspan = (
            2
            if ano == ano_base
            else 3
        )

        partes.append(
            f"""
            <th colspan="{colspan}">
                31/12/{ano}
            </th>
            """
        )

    partes.append(
        "</tr><tr>"
    )

    for ano in anos:

        partes.append(
            "<th>VA</th>"
        )

        partes.append(
            "<th>AV</th>"
        )

        if ano != ano_base:

            partes.append(
                "<th>AH</th>"
            )

    partes.append(
        "</tr></thead><tbody>"
    )

    for _, registro in (
        df.iterrows()
    ):

        linha = str(
            registro[
                "LINHA"
            ]
        )

        tipo = str(
            registro[
                "TIPO"
            ]
        )

        if tipo == "CABECALHO":

            classe = (
                "cabecalho"
            )

        elif linha_em_negrito(
            linha,
            tipo,
        ):

            classe = (
                "negrito"
            )

        else:

            classe = (
                "normal"
            )

        partes.append(
            f'<tr class="{classe}">'
        )

        partes.append(
            f"""
            <td class="descricao">
                {html.escape(linha)}
            </td>
            """
        )

        for ano in anos:

            if tipo == "CABECALHO":

                va = "—"
                av = "—"
                ah = "—"

            elif tipo == "SEM_CODIGO":

                va = "N/D"
                av = "N/D"
                ah = "N/D"

            else:

                va = formatar_va(
                    registro[
                        f"VA_{ano}"
                    ]
                )

                av = formatar_av(
                    registro[
                        f"AV_{ano}"
                    ]
                )

                ah = formatar_ah(
                    registro[
                        f"AH_{ano}"
                    ]
                )

            partes.append(
                f'<td class="numero">'
                f'{va}'
                f'</td>'
            )

            partes.append(
                f'<td class="numero">'
                f'{av}'
                f'</td>'
            )

            if ano != ano_base:

                partes.append(
                    f'<td class="numero">'
                    f'{ah}'
                    f'</td>'
                )

        partes.append(
            "</tr>"
        )

    partes.append(
        """
        </tbody>

        </table>

        </div>

        </body>

        </html>
        """
    )

    altura = max(
        430,
        145
        + len(df)
        * 35,
    )

    components.html(
        "".join(
            partes
        ),
        height=altura,
        scrolling=True,
    )


# ============================================================
# AUDITORIA
# ============================================================

def preparar_raw_exibicao(
    df,
):

    if df.empty:
        return df

    resultado = (
        df.copy()
    )

    for coluna in (
        resultado.columns
    ):

        if isinstance(
            coluna,
            int,
        ):

            resultado[
                coluna
            ] = (
                resultado[
                    coluna
                ]
                .map(
                    formatar_raw
                )
            )

    return resultado


# ============================================================
# INDICADORES
# ============================================================

def tabela_indicadores_grupo(
    quadro,
    grupo,
    anos_desc,
):

    parte = quadro.loc[
        quadro[
            "GRUPO"
        ] == grupo
    ].copy()

    registros = []

    for _, linha in (
        parte.iterrows()
    ):

        codigo = str(
            linha[
                "INDICADOR"
            ]
        )

        registro = {
            "Sigla": codigo,
            "Indicador": (
                NOMES_INDICADORES[
                    codigo
                ]
            ),
            "Unidade": (
                linha[
                    "UNIDADE"
                ]
            ),
        }

        for ano in anos_desc:

            valor = (
                linha[
                    ano
                ]
                if ano
                in linha.index
                else pd.NA
            )

            registro[
                str(
                    ano
                )
            ] = (
                formatar_indicador(
                    codigo,
                    valor,
                )
            )

        registro[
            "Leitura objetiva"
        ] = (
            LEITURAS_INDICADORES[
                codigo
            ]
        )

        registros.append(
            registro
        )

    return pd.DataFrame(
        registros
    )


# ============================================================
# RELATÓRIO — TABELA
# ============================================================

def montar_tabela_relatorio(
    analise,
    anos_analise,
):

    if analise.empty:

        return (
            pd.DataFrame()
        )

    anos = sorted(
        anos_analise
    )

    ano_base = (
        anos[0]
    )

    ano_recente = (
        anos[-1]
    )

    ano_intermediario = (
        anos[1]
        if len(anos) >= 3
        else None
    )

    registros = []

    for _, linha in (
        analise.iterrows()
    ):

        codigo = str(
            linha[
                "INDICADOR"
            ]
        )

        registro = {
            "Sigla": (
                codigo
            ),
            "Indicador": (
                linha[
                    "NOME"
                ]
            ),
            str(
                ano_base
            ): (
                formatar_indicador(
                    codigo,
                    linha[
                        "BASE"
                    ],
                )
            ),
        }

        if ano_intermediario is not None:

            registro[
                str(
                    ano_intermediario
                )
            ] = (
                formatar_indicador(
                    codigo,
                    linha[
                        "INTERMEDIARIO"
                    ],
                )
            )

        registro[
            str(
                ano_recente
            )
        ] = (
            formatar_indicador(
                codigo,
                linha[
                    "RECENTE"
                ],
            )
        )

        registro[
            "Variação base → recente"
        ] = (
            linha[
                "DELTA"
            ]
        )

        registro[
            "Trajetória"
        ] = (
            linha[
                "TRAJETORIA"
            ]
        )

        registros.append(
            registro
        )

    return pd.DataFrame(
        registros
    )


# ============================================================
# DASHBOARD — CARDS
# ============================================================

def exibir_cards_dashboard(
    cards,
    codigos,
    ano_base,
):

    if cards.empty:
        return

    parte = cards.loc[
        cards[
            "INDICADOR"
        ].isin(
            codigos
        )
    ]

    ordem = {
        codigo: indice
        for indice, codigo
        in enumerate(
            codigos
        )
    }

    parte = (
        parte
        .assign(
            _ORDEM=parte[
                "INDICADOR"
            ].map(
                ordem
            )
        )
        .sort_values(
            "_ORDEM"
        )
    )

    colunas = st.columns(
        len(
            codigos
        )
    )

    for indice, (
        _,
        linha,
    ) in enumerate(
        parte.iterrows()
    ):

        codigo = (
            linha[
                "INDICADOR"
            ]
        )

        with colunas[
            indice
        ]:

            st.metric(
                label=(
                    f"{codigo} — "
                    f"{NOMES_INDICADORES[codigo]}"
                ),
                value=(
                    linha[
                        "VALOR_RECENTE_FMT"
                    ]
                ),
            )

            st.caption(
                f"vs. {ano_base}: "
                f"{linha['DELTA_FMT']}"
            )


# ============================================================
# CATÁLOGO
# ============================================================

try:

    empresas = (
        carregar_empresas()
    )

except Exception as erro:

    st.error(
        "Não foi possível carregar "
        "o catálogo de empresas."
    )

    st.exception(
        erro
    )

    st.stop()


# ============================================================
# CABEÇALHO
# ============================================================

st.title(
    "Sistema CVM — Análise Financeira"
)

st.caption(
    "Demonstrações Financeiras Padronizadas da CVM | "
    "Modelo acadêmico padronizado | "
    "Valores monetários em R$ mil"
)

st.divider()


# ============================================================
# EMPRESA
# ============================================================

st.subheader(
    "Selecionar companhia"
)

termo_busca = st.text_input(
    "Pesquisar empresa",
    placeholder=(
        "Digite nome, CD_CVM ou CNPJ "
        "— exemplo: VALE, WEG, PETROBRAS..."
    ),
)

empresa_selecionada = (
    None
)


if termo_busca:

    resultados = (
        pesquisar_empresas(
            empresas,
            termo_busca,
        )
    )

    if resultados.empty:

        st.warning(
            "Nenhuma companhia encontrada."
        )

    else:

        st.caption(
            f"{len(resultados)} "
            "resultado(s) encontrado(s)"
        )

        rotulos = {}

        for _, linha in (
            resultados.iterrows()
        ):

            cd = str(
                linha[
                    "CD_CVM"
                ]
            )

            cnpj_rotulo = (
                formatar_cnpj(
                    linha[
                        "CNPJ_CIA"
                    ]
                )
            )

            nome_rotulo = str(
                linha[
                    "DENOM_CIA"
                ]
            )

            rotulos[
                cd
            ] = (
                f"{nome_rotulo}"
                f"  |  CVM {cd}"
                f"  |  {cnpj_rotulo}"
            )

        opcoes = list(
            rotulos.keys()
        )

        if (
            "seletor_empresa"
            in st.session_state
            and st.session_state[
                "seletor_empresa"
            ]
            not in opcoes
        ):

            del st.session_state[
                "seletor_empresa"
            ]

        cd_selecionado = (
            st.selectbox(
                "Companhia",
                options=opcoes,
                format_func=lambda cd: (
                    rotulos[
                        cd
                    ]
                ),
                key=(
                    "seletor_empresa"
                ),
            )
        )

        empresa_selecionada = (
            resultados.loc[
                resultados[
                    "CD_CVM"
                ]
                == cd_selecionado
            ]
            .iloc[
                0
            ]
            .copy()
        )


# ============================================================
# SISTEMA
# ============================================================

if empresa_selecionada is not None:

    cd_cvm = str(
        empresa_selecionada[
            "CD_CVM"
        ]
    )

    cnpj = str(
        empresa_selecionada[
            "CNPJ_CIA"
        ]
    )

    nome = str(
        empresa_selecionada[
            "DENOM_CIA"
        ]
    )

    st.divider()

    st.markdown(
        f"""
        <h2
            class="notranslate"
            translate="no"
        >
            {html.escape(nome)}
        </h2>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = (
        st.columns(
            3
        )
    )

    with c1:

        st.metric(
            "CD_CVM",
            cd_cvm,
        )

    with c2:

        st.metric(
            "CNPJ",
            formatar_cnpj(
                cnpj
            ),
        )

    with c3:

        st.metric(
            "Fonte",
            "DFP consolidada",
        )


    # ========================================================
    # ANOS
    # ========================================================

    try:

        resumo = (
            carregar_resumo_empresa(
                cd_cvm
            )
        )

        anos_disponiveis = sorted(
            {
                int(
                    ano
                )
                for ano
                in resumo.get(
                    "ANOS_DISPONIVEIS",
                    [],
                )
            }
        )

    except Exception as erro:

        st.error(
            "Erro ao identificar "
            "os exercícios disponíveis."
        )

        st.exception(
            erro
        )

        st.stop()


    if not anos_disponiveis:

        st.warning(
            "Nenhum exercício disponível."
        )

        st.stop()


    st.divider()

    st.subheader(
        "Período de análise"
    )

    ca, cp = (
        st.columns(
            [
                1,
                2,
            ]
        )
    )

    opcoes_ano = sorted(
        anos_disponiveis,
        reverse=True,
    )

    if (
        "exercicio_recente"
        in st.session_state
        and st.session_state[
            "exercicio_recente"
        ]
        not in opcoes_ano
    ):

        del st.session_state[
            "exercicio_recente"
        ]

    with ca:

        ano_recente = (
            st.selectbox(
                "Exercício mais recente",
                options=opcoes_ano,
                key=(
                    "exercicio_recente"
                ),
            )
        )

    anos_esperados = [
        ano_recente - 2,
        ano_recente - 1,
        ano_recente,
    ]

    anos_analise = [
        ano
        for ano
        in anos_esperados
        if ano
        in anos_disponiveis
    ]

    if not anos_analise:

        st.error(
            "Nenhum exercício compatível."
        )

        st.stop()

    anos_desc = sorted(
        anos_analise,
        reverse=True,
    )

    with cp:

        st.info(
            "Período: **"
            + " | ".join(
                str(
                    ano
                )
                for ano
                in anos_desc
            )
            + "**"
        )

    anos_tuple = tuple(
        sorted(
            anos_analise
        )
    )

    ano_base = min(
        anos_analise
    )


    # ========================================================
    # CARGA PRINCIPAL
    # ========================================================

    try:

        with st.spinner(
            "Montando análise financeira..."
        ):

            bpa = carregar_padronizada(
                cd_cvm,
                "BPA",
                anos_tuple,
            )

            bpp = carregar_padronizada(
                cd_cvm,
                "BPP",
                anos_tuple,
            )

            dre = carregar_padronizada(
                cd_cvm,
                "DRE",
                anos_tuple,
            )

            quadro_inds = (
                carregar_indicadores(
                    cd_cvm,
                    anos_tuple,
                )
            )

            relatorio = (
                carregar_relatorio(
                    cd_cvm,
                    nome,
                    anos_tuple,
                )
            )

            validacao = (
                carregar_validacao(
                    cd_cvm,
                    anos_tuple,
                )
            )

            cards_dashboard = (
                montar_cards_dashboard(
                    quadro_inds,
                    anos_tuple,
                )
            )

            graficos_dashboard = (
                montar_graficos_dashboard(
                    quadro_inds,
                    anos_tuple,
                )
            )

    except Exception as erro:

        st.error(
            "Erro ao montar "
            "a análise."
        )

        st.exception(
            erro
        )

        st.stop()


    # ========================================================
    # EXPORTAÇÃO
    # ========================================================

    identificacao_exportacao = {
        "DENOM_CIA": nome,
        "CD_CVM": cd_cvm,
        "CNPJ_CIA": cnpj,
    }

    try:

        arquivo_excel = (
            gerar_excel_sistema(
                identificacao=identificacao_exportacao,
                bp_ativo=bpa,
                bp_passivo=bpp,
                dre=dre,
                indicadores=quadro_inds,
                relatorio=relatorio,
                validacao=validacao,
                anos=list(
                    anos_tuple
                ),
                status_validacao=relatorio[
                    "STATUS_VALIDACAO"
                ],
            )
        )

        nome_arquivo_excel = (
            nome_arquivo_exportacao(
                identificacao_exportacao,
                anos=list(
                    anos_tuple
                ),
            )
        )

        erro_exportacao = None

    except Exception as erro:

        arquivo_excel = None
        nome_arquivo_excel = None
        erro_exportacao = erro


    st.divider()

    st.markdown(
        "### Exportar análise"
    )

    coluna_exportar, coluna_descricao = (
        st.columns(
            [
                1,
                3,
            ]
        )
    )

    with coluna_exportar:

        if arquivo_excel is not None:

            st.download_button(
                label="Exportar Excel completo",
                data=arquivo_excel,
                file_name=nome_arquivo_excel,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
                type="primary",
                key=(
                    f"download_excel_"
                    f"{cd_cvm}_"
                    f"{ano_recente}"
                ),
            )

        else:

            st.button(
                "Exportação indisponível",
                disabled=True,
                use_container_width=True,
            )

    with coluna_descricao:

        st.caption(
            "O arquivo inclui Identificação, BP Ativo, BP Passivo, "
            "DRE, os 12 Indicadores, Relatório e Validação/Auditoria. "
            "A exportação utiliza os mesmos resultados exibidos no "
            "sistema e não recalcula os indicadores."
        )

        if erro_exportacao is not None:

            st.warning(
                "A análise permanece disponível no sistema, "
                "mas não foi possível gerar o arquivo Excel."
            )

            with st.expander(
                "Detalhes técnicos da exportação"
            ):

                st.exception(
                    erro_exportacao
                )


    # ========================================================
    # ABAS
    # ========================================================

    st.divider()

    abas = st.tabs(
        [
            "Painel",
            "BP Ativo",
            "BP Passivo",
            "DRE",
            "Indicadores",
            "Relatório",
            "Metodologia / Auditoria",
        ]
    )


    # ========================================================
    # PAINEL
    # ========================================================

    with abas[0]:

        st.subheader(
            "Painel Executivo"
        )

        st.caption(
            "Síntese visual dos 12 indicadores financeiros. "
            "Os valores são provenientes diretamente do "
            "motor de indicadores e não são recalculados "
            "pelo painel."
        )


        # ----------------------------------------------------
        # CONTEXTO
        # ----------------------------------------------------

        contexto1, contexto2, contexto3, contexto4 = (
            st.columns(
                4
            )
        )

        with contexto1:

            st.metric(
                "Exercício recente",
                ano_recente,
            )

        with contexto2:

            st.metric(
                "Ano-base",
                ano_base,
            )

        with contexto3:

            st.metric(
                "Indicadores disponíveis",
                (
                    f"{len(cards_dashboard)} / 12"
                ),
            )

        with contexto4:

            st.metric(
                "Validação",
                relatorio[
                    "STATUS_VALIDACAO"
                ],
            )


        st.divider()


        # ----------------------------------------------------
        # ESTRUTURA
        # ----------------------------------------------------

        st.markdown(
            "## Estrutura de Capital"
        )

        exibir_cards_dashboard(
            cards_dashboard,
            [
                "IPL",
                "PCT",
                "CE",
                "EFSAT",
            ],
            ano_base,
        )

        st.plotly_chart(
            graficos_dashboard[
                "estrutura"
            ],
            use_container_width=True,
            key="grafico_estrutura_dashboard",
        )

        st.caption(
            "IPL, PCT, CE e EFSAT são apresentados "
            "em percentual. PCT, CE e EFSAT exigem "
            "interpretação contextual."
        )


        st.divider()


        # ----------------------------------------------------
        # LIQUIDEZ
        # ----------------------------------------------------

        st.markdown(
            "## Liquidez"
        )

        exibir_cards_dashboard(
            cards_dashboard,
            [
                "LG",
                "LC",
                "LS",
                "ICJ",
            ],
            ano_base,
        )

        coluna_liquidez, coluna_icj = (
            st.columns(
                [
                    2,
                    1,
                ]
            )
        )

        with coluna_liquidez:

            st.plotly_chart(
                graficos_dashboard[
                    "liquidez"
                ],
                use_container_width=True,
                key="grafico_liquidez_dashboard",
            )

        with coluna_icj:

            st.plotly_chart(
                graficos_dashboard[
                    "icj"
                ],
                use_container_width=True,
                key="grafico_icj_dashboard",
            )

        st.caption(
            "LG, LC e LS são razões. "
            "O ICJ é apresentado separadamente "
            "por possuir escala própria em vezes."
        )


        st.divider()


        # ----------------------------------------------------
        # DESEMPENHO
        # ----------------------------------------------------

        st.markdown(
            "## Lucratividade e Desempenho"
        )

        exibir_cards_dashboard(
            cards_dashboard,
            [
                "GA",
                "RSV",
                "ROA",
                "ROE",
            ],
            ano_base,
        )

        coluna_rentabilidade, coluna_ga = (
            st.columns(
                [
                    2,
                    1,
                ]
            )
        )

        with coluna_rentabilidade:

            st.plotly_chart(
                graficos_dashboard[
                    "rentabilidade"
                ],
                use_container_width=True,
                key="grafico_rentabilidade_dashboard",
            )

        with coluna_ga:

            st.plotly_chart(
                graficos_dashboard[
                    "ga"
                ],
                use_container_width=True,
                key="grafico_ga_dashboard",
            )

        st.caption(
            "RSV, ROA e ROE são percentuais. "
            "O Giro do Ativo é apresentado separadamente "
            "por utilizar unidade em vezes."
        )


        st.divider()


        # ----------------------------------------------------
        # LEITURA RÁPIDA
        # ----------------------------------------------------

        st.markdown(
            "## Leitura rápida"
        )

        st.markdown(
            relatorio[
                "RESUMO_EXECUTIVO"
            ]
        )

        st.caption(
            "Para interpretação detalhada, consulte "
            "as abas Indicadores e Relatório."
        )


    # ========================================================
    # BP ATIVO
    # ========================================================

    with abas[1]:

        st.subheader(
            "Balanço Patrimonial — Ativo"
        )

        st.caption(
            f"VA = Valor Absoluto em R$ mil | "
            f"AV = Análise Vertical | "
            f"AH = índice base fixa "
            f"{ano_base} = 100"
        )

        renderizar_tabela_padronizada(
            bpa,
            nome,
            "BALANÇOS PATRIMONIAIS EM",
        )

        with st.expander(
            "Ver BP Ativo completo da CVM — auditoria"
        ):

            raw = (
                preparar_raw_exibicao(
                    carregar_raw(
                        cd_cvm,
                        "BPA",
                        anos_tuple,
                    )
                )
            )

            st.dataframe(
                raw,
                use_container_width=True,
                hide_index=True,
                height=500,
            )


    # ========================================================
    # BP PASSIVO
    # ========================================================

    with abas[2]:

        st.subheader(
            "Balanço Patrimonial — "
            "Passivo e Patrimônio Líquido"
        )

        st.caption(
            f"VA = Valor Absoluto em R$ mil | "
            f"AV = Análise Vertical | "
            f"AH = índice base fixa "
            f"{ano_base} = 100"
        )

        renderizar_tabela_padronizada(
            bpp,
            nome,
            "BALANÇOS PATRIMONIAIS EM",
        )

        with st.expander(
            "Ver BP Passivo completo da CVM — auditoria"
        ):

            raw = (
                preparar_raw_exibicao(
                    carregar_raw(
                        cd_cvm,
                        "BPP",
                        anos_tuple,
                    )
                )
            )

            st.dataframe(
                raw,
                use_container_width=True,
                hide_index=True,
                height=500,
            )


    # ========================================================
    # DRE
    # ========================================================

    with abas[3]:

        st.subheader(
            "Demonstração do Resultado"
        )

        st.caption(
            f"VA = Valor Absoluto em R$ mil | "
            f"AV = Análise Vertical | "
            f"AH = índice base fixa "
            f"{ano_base} = 100"
        )

        renderizar_tabela_padronizada(
            dre,
            nome,
            (
                "DEMONSTRAÇÃO DO RESULTADO "
                "DO EXERCÍCIO FINDO EM"
            ),
        )

        st.caption(
            "* Valores não recorrentes permanecem "
            "N/D quando não existe CD_CONTA único "
            "e confiável."
        )

        with st.expander(
            "Ver DRE completa da CVM — auditoria"
        ):

            raw = (
                preparar_raw_exibicao(
                    carregar_raw(
                        cd_cvm,
                        "DRE",
                        anos_tuple,
                    )
                )
            )

            st.dataframe(
                raw,
                use_container_width=True,
                hide_index=True,
                height=500,
            )


    # ========================================================
    # INDICADORES
    # ========================================================

    with abas[4]:

        st.subheader(
            "Indicadores Financeiros"
        )

        st.caption(
            "Indicadores calculados diretamente "
            "pelo motor financeiro validado. "
            "Não se aplica AV ou AH aos indicadores."
        )

        if quadro_inds.empty:

            st.warning(
                "Indicadores não disponíveis."
            )

        else:

            for grupo in [
                "Estrutura de Capital",
                "Liquidez",
                "Lucratividade/Desempenho",
            ]:

                st.markdown(
                    f"### {grupo}"
                )

                tabela = (
                    tabela_indicadores_grupo(
                        quadro_inds,
                        grupo,
                        anos_desc,
                    )
                )

                st.dataframe(
                    tabela,
                    use_container_width=True,
                    hide_index=True,
                )


            st.divider()


            # =================================================
            # DETALHAMENTO
            # =================================================

            st.subheader(
                "Detalhamento do cálculo"
            )

            col_ind, col_ano = (
                st.columns(
                    2
                )
            )

            with col_ind:

                indicador_escolhido = (
                    st.selectbox(
                        "Indicador",
                        options=(
                            ORDEM_INDICADORES
                        ),
                        format_func=lambda x: (
                            f"{x} — "
                            f"{NOMES_INDICADORES[x]}"
                        ),
                        key=(
                            "indicador_detalhe"
                        ),
                    )
                )

            with col_ano:

                ano_detalhe = (
                    st.selectbox(
                        "Exercício",
                        options=anos_desc,
                        key=(
                            "ano_detalhe"
                        ),
                    )
                )

            try:

                detalhe = (
                    carregar_detalhe_indicador(
                        cd_cvm,
                        ano_detalhe,
                        indicador_escolhido,
                    )
                )

                resultado = (
                    detalhe[
                        "RESULTADO"
                    ]
                )

                formula = (
                    detalhe[
                        "FORMULA"
                    ]
                )

                st.metric(
                    (
                        f"{indicador_escolhido} — "
                        f"{NOMES_INDICADORES[indicador_escolhido]}"
                    ),
                    formatar_indicador(
                        indicador_escolhido,
                        resultado,
                    ),
                )

                st.markdown(
                    "**Fórmula utilizada**"
                )

                st.code(
                    formula,
                    language=None,
                )

                componentes = (
                    detalhe[
                        "COMPONENTES"
                    ]
                )

                linhas_componentes = []

                for chave in (
                    COMPONENTES_INDICADORES[
                        indicador_escolhido
                    ]
                ):

                    valor = (
                        componentes.get(
                            chave
                        )
                    )

                    linhas_componentes.append(
                        {
                            "Componente": (
                                ROTULOS_COMPONENTES.get(
                                    chave,
                                    chave,
                                )
                            ),

                            "Código interno": (
                                chave
                            ),

                            "Valor (R$ mil)": (
                                formatar_va(
                                    valor
                                )
                                if valor is not None
                                else "N/D"
                            ),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(
                        linhas_componentes
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            except Exception as erro:

                st.error(
                    "Não foi possível detalhar "
                    "o indicador selecionado."
                )

                st.exception(
                    erro
                )


            # =================================================
            # DUPONT
            # =================================================

            with st.expander(
                "Validação DuPont — ROA = GA × RSV"
            ):

                try:

                    dupont = (
                        carregar_dupont(
                            cd_cvm,
                            anos_tuple,
                        )
                    )

                    if dupont.empty:

                        st.warning(
                            "Validação DuPont "
                            "não disponível."
                        )

                    else:

                        linhas_dupont = []

                        for _, linha in (
                            dupont.iterrows()
                        ):

                            diferenca = (
                                linha[
                                    "DIFERENCA"
                                ]
                            )

                            if (
                                diferenca is None
                                or pd.isna(
                                    diferenca
                                )
                            ):

                                dif_fmt = (
                                    "N/D"
                                )

                            else:

                                dif_fmt = (
                                    f"{float(diferenca):.2e}"
                                    .replace(
                                        ".",
                                        ",",
                                    )
                                )

                            linhas_dupont.append(
                                {
                                    "Ano": (
                                        int(
                                            linha[
                                                "ANO"
                                            ]
                                        )
                                    ),

                                    "GA": (
                                        formatar_indicador(
                                            "GA",
                                            linha[
                                                "GA"
                                            ],
                                        )
                                    ),

                                    "RSV": (
                                        formatar_indicador(
                                            "RSV",
                                            linha[
                                                "RSV"
                                            ],
                                        )
                                    ),

                                    "ROA": (
                                        formatar_indicador(
                                            "ROA",
                                            linha[
                                                "ROA"
                                            ],
                                        )
                                    ),

                                    "GA × RSV": (
                                        formatar_indicador(
                                            "ROA",
                                            linha[
                                                "GA_X_RSV"
                                            ],
                                        )
                                    ),

                                    "Diferença": (
                                        dif_fmt
                                    ),

                                    "Status": (
                                        linha[
                                            "STATUS"
                                        ]
                                    ),
                                }
                            )

                        st.dataframe(
                            pd.DataFrame(
                                linhas_dupont
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )

                        st.caption(
                            "A identidade é testada "
                            "com valores não arredondados."
                        )

                except Exception as erro:

                    st.error(
                        "Erro na validação DuPont."
                    )

                    st.exception(
                        erro
                    )


    # ========================================================
    # RELATÓRIO
    # ========================================================

    with abas[5]:

        st.subheader(
            "Relatório de Análise Financeira"
        )

        st.caption(
            "Interpretação automática dos três exercícios "
            "a partir dos resultados oficiais dos "
            "indicadores e das verificações de integridade."
        )

        status_relatorio = (
            relatorio[
                "STATUS_VALIDACAO"
            ]
        )


        # ====================================================
        # CABEÇALHO
        # ====================================================

        r1, r2, r3 = (
            st.columns(
                3
            )
        )

        with r1:

            st.metric(
                "Empresa",
                nome,
            )

        with r2:

            st.metric(
                "Período",
                (
                    f"{min(anos_analise)}"
                    f"–"
                    f"{max(anos_analise)}"
                ),
            )

        with r3:

            st.metric(
                "Validação",
                status_relatorio,
            )


        if status_relatorio == "OK":

            st.success(
                "Validação concluída sem "
                "alertas ou bloqueios."
            )

        elif status_relatorio == "INFO":

            st.info(
                "Validação concluída com "
                "informações técnicas adicionais."
            )

        elif status_relatorio == "ALERTA":

            st.warning(
                "O relatório contém ressalvas "
                "de validação."
            )

        else:

            st.error(
                "A interpretação conclusiva está "
                "suspensa por bloqueio de integridade."
            )


        # ====================================================
        # RESUMO
        # ====================================================

        st.markdown(
            "## Resumo executivo"
        )

        st.markdown(
            relatorio[
                "RESUMO_EXECUTIVO"
            ]
        )

        st.divider()


        # ====================================================
        # PRINCIPAIS MUDANÇAS
        # ====================================================

        st.markdown(
            "## Principais mudanças do período"
        )

        principais = (
            relatorio[
                "PRINCIPAIS_MUDANCAS"
            ]
        )

        if principais:

            colunas_mudancas = (
                st.columns(
                    len(
                        principais
                    )
                )
            )

            for indice, item in enumerate(
                principais
            ):

                with colunas_mudancas[
                    indice
                ]:

                    st.markdown(
                        f"""
**Mudança {indice + 1}**

{item}
                        """
                    )

        else:

            st.info(
                "Não há mudanças classificadas "
                "para exibição."
            )

        st.divider()


        # ====================================================
        # EVOLUÇÃO
        # ====================================================

        st.markdown(
            "## Evolução dos indicadores"
        )

        analise_relatorio = (
            relatorio[
                "ANALISE_INDICADORES"
            ]
        )

        tabela_relatorio = (
            montar_tabela_relatorio(
                analise_relatorio,
                anos_analise,
            )
        )

        if not tabela_relatorio.empty:

            st.dataframe(
                tabela_relatorio,
                use_container_width=True,
                hide_index=True,
            )

        st.caption(
            "Para indicadores percentuais, a variação "
            "base → recente é apresentada em pontos "
            "percentuais. A trajetória considera os "
            "movimentos entre os três exercícios."
        )

        st.divider()


        # ====================================================
        # ANÁLISE POR GRUPO
        # ====================================================

        st.markdown(
            "## Análise por grupo"
        )

        sinteses = (
            relatorio[
                "SINTESES_GRUPOS"
            ]
        )

        if sinteses:

            grupo_estrutura, grupo_liquidez, grupo_desempenho = (
                st.tabs(
                    [
                        "Estrutura de Capital",
                        "Liquidez",
                        "Desempenho",
                    ]
                )
            )

            with grupo_estrutura:

                st.markdown(
                    sinteses.get(
                        "Estrutura de Capital",
                        "N/D",
                    )
                )

            with grupo_liquidez:

                st.markdown(
                    sinteses.get(
                        "Liquidez",
                        "N/D",
                    )
                )

            with grupo_desempenho:

                st.markdown(
                    sinteses.get(
                        "Lucratividade/Desempenho",
                        "N/D",
                    )
                )

        else:

            st.warning(
                "As sínteses por grupo estão "
                "suspensas devido à validação."
            )

        st.divider()


        # ====================================================
        # ANÁLISE INDIVIDUAL
        # ====================================================

        st.markdown(
            "## Análise individual dos indicadores"
        )

        if not analise_relatorio.empty:

            for grupo in [
                "Estrutura de Capital",
                "Liquidez",
                "Lucratividade/Desempenho",
            ]:

                st.markdown(
                    f"### {grupo}"
                )

                parte = (
                    analise_relatorio.loc[
                        analise_relatorio[
                            "GRUPO"
                        ] == grupo
                    ]
                )

                for _, linha in (
                    parte.iterrows()
                ):

                    codigo = (
                        linha[
                            "INDICADOR"
                        ]
                    )

                    titulo_expander = (
                        f"{codigo} — "
                        f"{linha['NOME']} | "
                        f"{linha['TRAJETORIA']}"
                    )

                    with st.expander(
                        titulo_expander
                    ):

                        e1, e2, e3 = (
                            st.columns(
                                3
                            )
                        )

                        with e1:

                            st.metric(
                                str(
                                    min(
                                        anos_analise
                                    )
                                ),
                                formatar_indicador(
                                    codigo,
                                    linha[
                                        "BASE"
                                    ],
                                ),
                            )

                        with e2:

                            if len(
                                anos_analise
                            ) >= 3:

                                st.metric(
                                    str(
                                        sorted(
                                            anos_analise
                                        )[1]
                                    ),
                                    formatar_indicador(
                                        codigo,
                                        linha[
                                            "INTERMEDIARIO"
                                        ],
                                    ),
                                )

                        with e3:

                            st.metric(
                                str(
                                    max(
                                        anos_analise
                                    )
                                ),
                                formatar_indicador(
                                    codigo,
                                    linha[
                                        "RECENTE"
                                    ],
                                ),
                            )

                        st.markdown(
                            f"**Variação base → recente:** "
                            f"{linha['DELTA']}"
                        )

                        st.markdown(
                            f"**Trajetória:** "
                            f"{linha['TRAJETORIA']}"
                        )

                        st.markdown(
                            linha[
                                "INTERPRETACAO"
                            ]
                        )

        st.divider()


        # ====================================================
        # DUPONT
        # ====================================================

        st.markdown(
            "## Decomposição DuPont"
        )

        dupont_relatorio = (
            relatorio[
                "DUPONT"
            ]
        )

        if not dupont_relatorio.empty:

            dupont_exibicao = (
                dupont_relatorio.copy()
            )

            for coluna in [
                "GA",
                "RSV",
                "ROA",
                "GA_X_RSV",
            ]:

                if coluna in (
                    dupont_exibicao.columns
                ):

                    indicador_fmt = (
                        "GA"
                        if coluna == "GA"
                        else (
                            "ROA"
                            if coluna
                            in {
                                "ROA",
                                "GA_X_RSV",
                            }
                            else "RSV"
                        )
                    )

                    dupont_exibicao[
                        coluna
                    ] = [
                        formatar_indicador(
                            indicador_fmt,
                            valor,
                        )
                        for valor in (
                            dupont_exibicao[
                                coluna
                            ]
                        )
                    ]

            dupont_exibicao = (
                dupont_exibicao.rename(
                    columns={
                        "GA_X_RSV": (
                            "GA × RSV"
                        ),
                    }
                )
            )

            st.dataframe(
                dupont_exibicao[
                    [
                        "ANO",
                        "GA",
                        "RSV",
                        "ROA",
                        "GA × RSV",
                        "STATUS",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "ROA = Giro do Ativo × "
                "Retorno sobre Vendas. "
                "A validação utiliza valores "
                "não arredondados."
            )

        st.divider()


        # ====================================================
        # PONTOS DE ATENÇÃO
        # ====================================================

        st.markdown(
            "## Pontos de atenção"
        )

        pontos = (
            relatorio[
                "PONTOS_ATENCAO"
            ]
        )

        for ponto in pontos:

            if str(
                ponto
            ).startswith(
                "BLOQUEIO"
            ):

                st.error(
                    ponto
                )

            elif str(
                ponto
            ).startswith(
                "ALERTA"
            ):

                st.warning(
                    ponto
                )

            elif (
                "Nenhum alerta"
                in str(
                    ponto
                )
            ):

                st.success(
                    ponto
                )

            else:

                st.info(
                    ponto
                )

        st.divider()


        # ====================================================
        # CONCLUSÃO
        # ====================================================

        st.markdown(
            "## Conclusão"
        )

        st.markdown(
            relatorio[
                "CONCLUSAO"
            ]
        )

        st.divider()


        with st.expander(
            "Metodologia do relatório"
        ):

            st.markdown(
                """
O relatório é gerado por regras determinísticas.

- Utiliza os mesmos 12 indicadores apresentados na aba **Indicadores**.
- Não recalcula BP, DRE ou indicadores em paralelo.
- Compara exercício-base, intermediário e recente.
- Indicadores percentuais utilizam diferenças em pontos percentuais.
- As trajetórias distinguem crescimento, redução, recuperação, reversão e estabilidade.
- PCT, CE e EFSAT recebem interpretação contextual.
- A decomposição DuPont utiliza `ROA = GA × RSV`.
- Dados ausentes permanecem `N/D`.
- Bloqueios de integridade suspendem conclusões financeiras.
- Não é atribuída pontuação automática de saúde financeira.
                """
            )


    # ========================================================
    # METODOLOGIA / AUDITORIA
    # ========================================================

    with abas[6]:

        st.subheader(
            "Metodologia e Auditoria"
        )

        periodo_texto = (
            " | ".join(
                str(
                    ano
                )
                for ano
                in anos_desc
            )
        )

        st.markdown(
            f"""
**Empresa:** {nome}

**CD_CVM:** {cd_cvm}

**Período:** {periodo_texto}

**Unidade das demonstrações:** R$ mil

### Análise Vertical

- BP Ativo: rubrica / Ativo Total.
- BP Passivo: rubrica / Passivo Total.
- DRE: rubrica / Receita Líquida.

### Análise Horizontal

- índice de base fixa;
- ano-base = {ano_base} = 100;
- o ano-base não exibe AH;
- base zero ou ausente = N/D.

### Indicadores

- Estrutura de Capital: IPL, PCT, CE e EFSAT.
- Liquidez: LG, LC, LS e ICJ.
- Lucratividade/Desempenho: GA, RSV, ROA e ROE.
- DuPont: ROA = GA × RSV.

### Painel

- consome os resultados oficiais dos 12 indicadores;
- gráficos em ordem cronológica;
- ICJ e GA são separados por unidade e escala;
- não utiliza semáforos de desempenho financeiro;
- variações dos cards são informativas e não representam julgamento.

### Relatório

- consome os resultados oficiais dos indicadores;
- utiliza regras narrativas determinísticas;
- identifica trajetórias;
- mostra variação base → recente;
- integra validação e DuPont;
- não atribui notas ou semáforos financeiros arbitrários.
            """
        )

        st.warning(
            "Dado ausente não é convertido em zero. "
            "Contas agregadas usam somente os "
            "CD_CONTA definidos metodologicamente."
        )


# ============================================================
# ESTADO INICIAL
# ============================================================

else:

    if not termo_busca:

        st.info(
            "Pesquise uma companhia "
            "para iniciar a análise."
        )
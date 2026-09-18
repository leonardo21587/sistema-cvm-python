from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.demonstracoes import montar_quadro_demonstracao
from src.banco import carregar_demonstracao
from src.layouts_cvm import LAYOUT_PADRAO, detectar_layout


# ============================================================
# CONFIGURAÇÃO
# ============================================================

TIPOS_VALIDOS = {
    "DIRETA",
    "SOMA",
    "CALCULADA",
    "CABECALHO",
    "SEM_CODIGO",
}


BASE_AV = {
    "BPA": "1",
    "BPP": "2",
    "DRE": "3.01",
}


# ============================================================
# MAPA PADRONIZADO — PROFESSOR
# ============================================================

MAPA_BPA = [

    {
        "linha": "TOTAL ATIVO",
        "tipo": "DIRETA",
        "codigos": ["1"],
    },

    {
        "linha": "ATIVO CIRCULANTE",
        "tipo": "DIRETA",
        "codigos": ["1.01"],
    },

    {
        "linha": "FINANCEIRO",
        "tipo": "CABECALHO",
        "codigos": [],
    },

    {
        "linha": "Disponível",
        "tipo": "DIRETA",
        "codigos": ["1.01.01"],
    },

    {
        "linha": "Aplicações de Liquidez e TVM",
        "tipo": "DIRETA",
        "codigos": ["1.01.02"],
    },

    {
        "linha": "OPERACIONAL",
        "tipo": "CABECALHO",
        "codigos": [],
    },

    {
        "linha": "Contas a receber",
        "tipo": "DIRETA",
        "codigos": ["1.01.03"],
    },

    {
        "linha": "Estoques",
        "tipo": "DIRETA",
        "codigos": ["1.01.04"],
    },

    {
        "linha": "Outros ativos circulantes",
        "tipo": "SOMA",
        "codigos": [
            "1.01.05",
            "1.01.06",
            "1.01.07",
            "1.01.08",
        ],
    },

    {
        "linha": "ATIVO NÃO CIRCULANTE",
        "tipo": "DIRETA",
        "codigos": ["1.02"],
    },

    {
        "linha": "Realizável a L.P. Contas a Receber",
        "tipo": "DIRETA",
        "codigos": ["1.02.01.04"],
    },

    {
        "linha": "Realizável a L.P. Estoques",
        "tipo": "DIRETA",
        "codigos": ["1.02.01.05"],
    },

    {
        "linha": "Demais Realizáveis a Longo Prazo",
        "tipo": "DIRETA",
        "codigos": ["1.02.01"],
    },

    {
        "linha": "Investimentos",
        "tipo": "DIRETA",
        "codigos": ["1.02.02"],
    },

    {
        "linha": "Imobilizado",
        "tipo": "DIRETA",
        "codigos": ["1.02.03"],
    },

    {
        "linha": "Intangível",
        "tipo": "DIRETA",
        "codigos": ["1.02.04"],
    },
]


MAPA_BPP = [

    {
        "linha": "TOTAL PASSIVO + PL",
        "tipo": "DIRETA",
        "codigos": ["2"],
    },

    {
        "linha": "PASSIVO CIRCULANTE",
        "tipo": "DIRETA",
        "codigos": ["2.01"],
    },

    {
        "linha": "OPERACIONAL",
        "tipo": "CABECALHO",
        "codigos": [],
    },

    {
        "linha": "Fornecedores",
        "tipo": "DIRETA",
        "codigos": ["2.01.02"],
    },

    {
        "linha": "Outras Obrigações",
        "tipo": "SOMA",
        "codigos": [
            "2.01.01",
            "2.01.03",
            "2.01.05",
            "2.01.06",
            "2.01.07",
        ],
    },

    {
        "linha": "FINANCEIRO",
        "tipo": "CABECALHO",
        "codigos": [],
    },

    {
        "linha": "Empréstimos e Financiamentos",
        "tipo": "DIRETA",
        "codigos": ["2.01.04"],
    },

    {
        "linha": "PASSIVO NÃO CIRCULANTE",
        "tipo": "DIRETA",
        "codigos": ["2.02"],
    },

    {
        "linha": "Empréstimos e Financiamentos",
        "tipo": "DIRETA",
        "codigos": ["2.02.01"],
    },

    {
        "linha": "Outras Obrigações",
        "tipo": "SOMA",
        "codigos": [
            "2.02.02",
            "2.02.03",
            "2.02.04",
            "2.02.05",
            "2.02.06",
        ],
    },

    {
        "linha": "TOTAL CAPITAL DE TERCEIROS",
        "tipo": "SOMA",
        "codigos": [
            "2.01",
            "2.02",
        ],
    },

    {
        "linha": "PATRIMÔNIO LÍQUIDO",
        "tipo": "DIRETA",
        "codigos": ["2.03"],
    },

    {
        "linha": "Capital, Reservas de Capital",
        "tipo": "SOMA",
        "codigos": [
            "2.03.01",
            "2.03.02",
            "2.03.09",
        ],
    },

    {
        "linha": "Reservas de lucros",
        "tipo": "SOMA",
        "codigos": [
            "2.03.04",
            "2.03.05",
        ],
    },

    {
        "linha": "Ajustes de Avaliação Patrimonial",
        "tipo": "SOMA",
        "codigos": [
            "2.03.03",
            "2.03.06",
            "2.03.07",
            "2.03.08",
        ],
    },
]


MAPA_DRE = [

    {
        "linha": "RECEITA LÍQUIDA",
        "tipo": "DIRETA",
        "codigos": ["3.01"],
    },

    {
        "linha": "(-) Custo dos Prod. Vend.",
        "tipo": "DIRETA",
        "codigos": ["3.02"],
    },

    {
        "linha": "(=) LUCRO BRUTO",
        "tipo": "DIRETA",
        "codigos": ["3.03"],
    },

    {
        "linha": "(-) Despesas com Vendas",
        "tipo": "DIRETA",
        "codigos": ["3.04.01"],
    },

    {
        "linha": "(-) Despesas Gerais e Adm.",
        "tipo": "DIRETA",
        "codigos": ["3.04.02"],
    },

    {
        "linha": "(±) Outras Rec./Desp. Oper.",
        "tipo": "SOMA",
        "codigos": [
            "3.04.04",
            "3.04.05",
        ],
    },

    {
        "linha": "(=) LUCRO OPERAC. I",
        "tipo": "DIRETA",
        "codigos": ["3.05"],
    },

    {
        "linha": "(+) Receitas Financeiras",
        "tipo": "DIRETA",
        "codigos": ["3.06.01"],
    },

    {
        "linha": "(-) Despesas Financeiras",
        "tipo": "DIRETA",
        "codigos": ["3.06.02"],
    },

    {
        "linha": "(=) LUCRO OPERAC. II",
        "tipo": "CALCULADA",
        "formula": "LOP2",
        "codigos": [
            "3.05",
            "3.06.01",
            "3.06.02",
        ],
    },

    {
        "linha": "(±) Res. da Equivalência Patrimonial",
        "tipo": "DIRETA",
        "codigos": ["3.04.06"],
    },

    {
        "linha": "(=) LUCRO OPERAC. III",
        "tipo": "DIRETA",
        "codigos": ["3.07"],
    },

    {
        "linha": "(-) IR e CS",
        "tipo": "DIRETA",
        "codigos": ["3.08"],
    },

    {
        "linha": "(=) RES. LÍQ. OPERAÇÕES CONTINUADAS",
        "tipo": "DIRETA",
        "codigos": ["3.09"],
    },

    {
        "linha": "(±) Valores não recorrentes*",
        "tipo": "SEM_CODIGO",
        "codigos": [],
    },

    {
        "linha": "(±) Res. Op. descontinuadas",
        "tipo": "DIRETA",
        "codigos": ["3.10"],
    },

    {
        "linha": "(=) RESULTADO LÍQUIDO DO PERÍODO",
        "tipo": "DIRETA",
        "codigos": ["3.11"],
    },
]


MAPAS = {
    "BPA": MAPA_BPA,
    "BPP": MAPA_BPP,
    "DRE": MAPA_DRE,
}


# ============================================================
# FUNÇÕES INTERNAS
# ============================================================

def _normalizar_cd_cvm(
    cd_cvm: str,
) -> str:

    return (
        str(cd_cvm)
        .strip()
        .zfill(6)
    )


def _anos_no_quadro(
    quadro: pd.DataFrame,
) -> list[int]:

    return sorted(
        coluna
        for coluna in quadro.columns
        if isinstance(
            coluna,
            int,
        )
    )


def _valor_codigo(
    quadro: pd.DataFrame,
    codigo: str,
    ano: int,
):

    linhas = quadro.loc[
        quadro["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq(str(codigo))
    ]

    if linhas.empty:
        return pd.NA

    if len(linhas) != 1:

        raise RuntimeError(
            "Conta encontrada mais de uma vez "
            "no quadro consolidado: "
            f"{codigo}"
        )

    valor = pd.to_numeric(
        linhas.iloc[0][ano],
        errors="coerce",
    )

    if pd.isna(valor):
        return pd.NA

    return float(valor)


def _somar_codigos(
    quadro: pd.DataFrame,
    codigos: list[str],
    ano: int,
):

    valores = [
        _valor_codigo(
            quadro,
            codigo,
            ano,
        )
        for codigo in codigos
    ]

    # Ausência não pode virar zero.
    if any(
        pd.isna(valor)
        for valor in valores
    ):
        return pd.NA

    return float(
        sum(valores)
    )


def _calcular_linha(
    quadro: pd.DataFrame,
    item: dict,
    ano: int,
):

    tipo = item["tipo"]

    if tipo not in TIPOS_VALIDOS:

        raise ValueError(
            f"Tipo de linha inválido: {tipo}"
        )

    if tipo == "CABECALHO":
        return pd.NA

    if tipo == "SEM_CODIGO":
        return pd.NA

    if tipo == "DIRETA":

        return _valor_codigo(
            quadro,
            item["codigos"][0],
            ano,
        )

    if tipo == "SOMA":

        return _somar_codigos(
            quadro,
            item["codigos"],
            ano,
        )

    if tipo == "CALCULADA":

        formula = item.get(
            "formula"
        )

        if formula == "LOP2":

            return _somar_codigos(
                quadro,
                item["codigos"],
                ano,
            )

        raise ValueError(
            "Fórmula calculada não reconhecida: "
            f"{formula}"
        )

    raise RuntimeError(
        f"Tipo não tratado: {tipo}"
    )


# ============================================================
# MONTAGEM DA DEMONSTRAÇÃO PADRONIZADA
# ============================================================

def montar_demonstracao_padronizada(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
) -> pd.DataFrame:

    cd_cvm = (
        _normalizar_cd_cvm(
            cd_cvm
        )
    )

    demonstracao = (
        str(demonstracao)
        .upper()
        .strip()
    )

    if demonstracao not in MAPAS:

        raise ValueError(
            "DEMONSTRACAO deve ser "
            "BPA, BPP ou DRE."
        )

    quadro = (
        montar_quadro_demonstracao(
            cd_cvm=cd_cvm,
            demonstracao=demonstracao,
            anos=anos,
            somente_contas_fixas=False,
        )
    )

    if quadro.empty:
        return pd.DataFrame()

    anos_quadro = (
        _anos_no_quadro(
            quadro
        )
    )

    if not anos_quadro:
        return pd.DataFrame()

    mapa = MAPAS[
        demonstracao
    ]

    registros = []

    for ordem, item in enumerate(
        mapa,
        start=1,
    ):

        registro = {
            "ORDEM": ordem,
            "LINHA": item["linha"],
            "TIPO": item["tipo"],
        }

        for ano in anos_quadro:

            registro[
                f"VA_{ano}"
            ] = _calcular_linha(
                quadro,
                item,
                ano,
            )

        registros.append(
            registro
        )

    resultado = pd.DataFrame(
        registros
    )


    # ========================================================
    # ANÁLISE VERTICAL
    # ========================================================

    codigo_base_av = (
        BASE_AV[
            demonstracao
        ]
    )

    bases_av = {
        ano: _valor_codigo(
            quadro,
            codigo_base_av,
            ano,
        )
        for ano in anos_quadro
    }

    for ano in anos_quadro:

        denominador = (
            bases_av[ano]
        )

        coluna_av = []

        for _, linha in (
            resultado.iterrows()
        ):

            tipo = linha["TIPO"]

            valor = linha[
                f"VA_{ano}"
            ]

            if tipo == "CABECALHO":

                coluna_av.append(
                    pd.NA
                )

                continue

            if tipo == "SEM_CODIGO":

                coluna_av.append(
                    pd.NA
                )

                continue

            if (
                pd.isna(valor)
                or pd.isna(
                    denominador
                )
                or float(
                    denominador
                ) == 0
            ):

                coluna_av.append(
                    pd.NA
                )

                continue

            coluna_av.append(
                float(valor)
                / float(denominador)
                * 100.0
            )

        resultado[
            f"AV_{ano}"
        ] = coluna_av


    # ========================================================
    # ANÁLISE HORIZONTAL
    # BASE FIXA
    # ========================================================

    ano_base = min(
        anos_quadro
    )

    for ano in anos_quadro:

        coluna_ah = []

        for _, linha in (
            resultado.iterrows()
        ):

            tipo = linha["TIPO"]

            valor_base = linha[
                f"VA_{ano_base}"
            ]

            valor_atual = linha[
                f"VA_{ano}"
            ]

            if tipo == "CABECALHO":

                coluna_ah.append(
                    pd.NA
                )

                continue

            if tipo == "SEM_CODIGO":

                coluna_ah.append(
                    pd.NA
                )

                continue

            if (
                pd.isna(
                    valor_base
                )
                or pd.isna(
                    valor_atual
                )
                or float(
                    valor_base
                ) == 0
            ):

                coluna_ah.append(
                    pd.NA
                )

                continue

            coluna_ah.append(
                float(valor_atual)
                / float(valor_base)
                * 100.0
            )

        resultado[
            f"AH_{ano}"
        ] = coluna_ah


    # ========================================================
    # ORDEM DAS COLUNAS
    # ========================================================

    anos_desc = sorted(
        anos_quadro,
        reverse=True,
    )

    colunas = [
        "ORDEM",
        "LINHA",
        "TIPO",
    ]

    for ano in anos_desc:

        colunas.extend(
            [
                f"VA_{ano}",
                f"AV_{ano}",
                f"AH_{ano}",
            ]
        )

    resultado = (
        resultado[
            colunas
        ]
        .sort_values(
            "ORDEM"
        )
        .reset_index(
            drop=True
        )
    )

    resultado.attrs[
        "DEMONSTRACAO"
    ] = demonstracao

    resultado.attrs[
        "ANO_BASE_AH"
    ] = ano_base

    resultado.attrs[
        "ANOS"
    ] = anos_desc

    return resultado


# ============================================================
# APRESENTAÇÃO CONSCIENTE DE LAYOUT
# ============================================================

def montar_demonstracao_apresentacao(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
) -> pd.DataFrame:
    # Mantém o modelo padronizado do professor para empresas
    # de layout padrão. Para layouts setoriais, apresenta as
    # contas fixas reais da CVM, sem forçar códigos de outro setor.
    cd_cvm = _normalizar_cd_cvm(
        cd_cvm
    )

    demonstracao = (
        str(demonstracao)
        .upper()
        .strip()
    )

    if demonstracao not in MAPAS:
        raise ValueError(
            "DEMONSTRACAO deve ser BPA, BPP ou DRE."
        )

    quadro_fixo = (
        montar_quadro_demonstracao(
            cd_cvm=cd_cvm,
            demonstracao=demonstracao,
            anos=anos,
            somente_contas_fixas=True,
        )
    )

    if quadro_fixo.empty:
        return pd.DataFrame()

    anos_quadro = _anos_no_quadro(
        quadro_fixo
    )

    if not anos_quadro:
        return pd.DataFrame()

    ano_recente = max(
        anos_quadro
    )

    bpp_recente = carregar_demonstracao(
        cd_cvm,
        ano_recente,
        "BPP",
    )

    dre_recente = carregar_demonstracao(
        cd_cvm,
        ano_recente,
        "DRE",
    )

    layout = detectar_layout(
        bpp_recente,
        dre_recente,
    )

    if layout.codigo == LAYOUT_PADRAO:
        resultado = (
            montar_demonstracao_padronizada(
                cd_cvm=cd_cvm,
                demonstracao=demonstracao,
                anos=anos,
            )
        )

        resultado.attrs["LAYOUT"] = layout.codigo
        resultado.attrs["APRESENTACAO_SETORIAL"] = False
        resultado.attrs["AV_NAO_APLICAVEL"] = False

        return resultado

    registros = []

    for ordem, (_, linha) in enumerate(
        quadro_fixo.iterrows(),
        start=1,
    ):
        codigo = str(
            linha["CD_CONTA"]
        ).strip()

        descricao = str(
            linha["DS_CONTA"]
        ).strip()

        registro = {
            "ORDEM": ordem,
            "LINHA": f"{codigo} — {descricao}",
            "TIPO": "DIRETA",
        }

        for ano in anos_quadro:
            registro[f"VA_{ano}"] = pd.to_numeric(
                linha.get(
                    ano,
                    pd.NA,
                ),
                errors="coerce",
            )

        registros.append(
            registro
        )

    resultado = pd.DataFrame(
        registros
    )

    if demonstracao == "BPA":
        codigo_base_av = "1"
    elif demonstracao == "BPP":
        codigo_base_av = "2"
    else:
        codigo_base_av = None

    for ano in anos_quadro:
        coluna_av = f"AV_{ano}"

        if codigo_base_av is None:
            resultado[coluna_av] = pd.NA
            continue

        linha_base = quadro_fixo.loc[
            quadro_fixo["CD_CONTA"]
            .astype(str)
            .str.strip()
            .eq(
                codigo_base_av
            )
        ]

        if len(linha_base) != 1:
            resultado[coluna_av] = pd.NA
            continue

        denominador = pd.to_numeric(
            linha_base.iloc[0].get(
                ano,
                pd.NA,
            ),
            errors="coerce",
        )

        if (
            pd.isna(denominador)
            or float(denominador) == 0
        ):
            resultado[coluna_av] = pd.NA
            continue

        resultado[coluna_av] = (
            pd.to_numeric(
                resultado[f"VA_{ano}"],
                errors="coerce",
            )
            / float(denominador)
            * 100.0
        )

    ano_base = min(
        anos_quadro
    )

    for ano in anos_quadro:
        valores_base = pd.to_numeric(
            resultado[f"VA_{ano_base}"],
            errors="coerce",
        )

        valores_atuais = pd.to_numeric(
            resultado[f"VA_{ano}"],
            errors="coerce",
        )

        valido = (
            valores_base.notna()
            & valores_atuais.notna()
            & valores_base.ne(0)
        )

        ah = pd.Series(
            pd.NA,
            index=resultado.index,
            dtype="Float64",
        )

        ah.loc[valido] = (
            valores_atuais.loc[valido]
            / valores_base.loc[valido]
            * 100.0
        )

        resultado[f"AH_{ano}"] = ah

    anos_desc = sorted(
        anos_quadro,
        reverse=True,
    )

    colunas = [
        "ORDEM",
        "LINHA",
        "TIPO",
    ]

    for ano in anos_desc:
        colunas.extend(
            [
                f"VA_{ano}",
                f"AV_{ano}",
                f"AH_{ano}",
            ]
        )

    resultado = (
        resultado[colunas]
        .sort_values("ORDEM")
        .reset_index(drop=True)
    )

    resultado.attrs["DEMONSTRACAO"] = demonstracao
    resultado.attrs["ANO_BASE_AH"] = ano_base
    resultado.attrs["ANOS"] = anos_desc
    resultado.attrs["LAYOUT"] = layout.codigo
    resultado.attrs["LAYOUT_DESCRICAO"] = layout.descricao
    resultado.attrs["APRESENTACAO_SETORIAL"] = True
    resultado.attrs["AV_NAO_APLICAVEL"] = (
        demonstracao == "DRE"
    )

    return resultado


# ============================================================
# TESTE DIRETO
# ============================================================

if __name__ == "__main__":

    pd.set_option(
        "display.max_columns",
        None,
    )

    pd.set_option(
        "display.width",
        240,
    )

    empresa_teste = "004170"

    anos_teste = [
        2023,
        2024,
        2025,
    ]

    for demonstracao in [
        "BPA",
        "BPP",
        "DRE",
    ]:

        print()
        print(
            "=" * 100
        )

        print(
            f"VALE - {demonstracao} "
            "- MODELO PADRONIZADO"
        )

        print(
            "=" * 100
        )

        teste = (
            montar_demonstracao_padronizada(
                cd_cvm=empresa_teste,
                demonstracao=demonstracao,
                anos=anos_teste,
            )
        )

        print(
            teste.to_string(
                index=False
            )
        )
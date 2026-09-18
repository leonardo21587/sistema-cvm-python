from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from config.settings import PROCESSED_DIR
from src.banco import (
    anos_disponiveis,
    carregar_demonstracao,
)
from src.layouts_cvm import (
    LAYOUT_PADRAO,
    detectar_layout,
    indicador_aplicavel,
    motivo_nao_aplicavel,
    normalizar_descricao,
)


ARQUIVO_AUXILIAR = (
    PROCESSED_DIR
    / "saldos_auxiliares_2022.parquet"
)


FORMULAS = {
    "IPL": "(Investimentos + Imobilizado + Intangível) / PL",
    "PCT": "(PC + PNC) / PL",
    "CE": "PC / (PC + PNC)",
    "EFSAT": "(Empréstimos CP + Empréstimos LP) / Ativo Total",
    "LG": "(AC + RLP) / (PC + PNC)",
    "LC": "AC / PC",
    "LS": "(Disponível + Aplicações Financeiras + Contas a Receber) / PC",
    "ICJ": "EBIT / ABS(Despesas Financeiras)",
    "GA": "Receita Líquida / Ativo Total Médio",
    "RSV": "Lucro Líquido / Receita Líquida",
    "ROA": "Lucro Líquido / Ativo Total Médio",
    "ROE": "Lucro Líquido / PL Médio Ajustado",
}


GRUPOS = {
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


UNIDADES = {
    "IPL": "%",
    "PCT": "%",
    "CE": "%",
    "EFSAT": "%",
    "LG": "razão",
    "LC": "razão",
    "LS": "razão",
    "ICJ": "vezes",
    "GA": "vezes",
    "RSV": "%",
    "ROA": "%",
    "ROE": "%",
}


PERCENTUAIS = {
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


def _normalizar_cd_cvm(
    cd_cvm: str,
) -> str:

    return (
        str(
            cd_cvm
        )
        .strip()
        .zfill(6)
    )


def _valor_conta(
    df: pd.DataFrame,
    codigo: str | None,
) -> float | None:

    if (
        df is None
        or df.empty
        or codigo is None
    ):
        return None

    linhas = df[
        df["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq(
            str(
                codigo
            )
        )
    ]

    if linhas.empty:
        return None

    if len(linhas) != 1:

        raise RuntimeError(
            f"Conta {codigo} encontrada "
            f"{len(linhas)} vezes na mesma "
            "demonstração/exercício."
        )

    valor = (
        linhas.iloc[0][
            "VL_CONTA"
        ]
    )

    if pd.isna(
        valor
    ):
        return None

    return float(
        valor
    )


def _valor_conta_descricao_exata(
    df: pd.DataFrame,
    descricao: str,
) -> float | None:

    if (
        df is None
        or df.empty
        or "DS_CONTA" not in df.columns
    ):
        return None

    alvo = normalizar_descricao(
        descricao
    )

    mascara = (
        df["DS_CONTA"]
        .map(
            normalizar_descricao
        )
        .eq(
            alvo
        )
    )

    linhas = df[
        mascara
    ]

    if linhas.empty:
        return None

    if len(linhas) != 1:
        return None

    valor = (
        linhas.iloc[0][
            "VL_CONTA"
        ]
    )

    if pd.isna(
        valor
    ):
        return None

    return float(
        valor
    )


def _dividir(
    numerador: float | None,
    denominador: float | None,
    absoluto_denominador: bool = False,
) -> float | None:

    if (
        numerador is None
        or denominador is None
    ):
        return None

    if absoluto_denominador:

        denominador = abs(
            denominador
        )

    if denominador == 0:
        return None

    return (
        numerador
        / denominador
    )


def _somar(
    *valores: float | None,
) -> float | None:

    if any(
        valor is None
        for valor in valores
    ):
        return None

    return float(
        sum(
            valores
        )
    )


def _media(
    inicial: float | None,
    final: float | None,
) -> float | None:

    if (
        inicial is None
        or final is None
    ):
        return None

    return (
        inicial
        + final
    ) / 2.0


def _pl_medio_ajustado(
    pl_inicial: float | None,
    pl_final: float | None,
    lucro_liquido: float | None,
) -> float | None:

    if (
        pl_inicial is None
        or pl_final is None
        or lucro_liquido is None
    ):
        return None

    return (
        pl_inicial
        + pl_final
        - lucro_liquido
    ) / 2.0


def _carregar_auxiliar_2022(
    cd_cvm: str,
) -> dict[str, float | None]:

    if not ARQUIVO_AUXILIAR.exists():

        raise FileNotFoundError(
            "Arquivo auxiliar não encontrado: "
            f"{ARQUIVO_AUXILIAR}. "
            "Execute primeiro: "
            "python src\\ano_auxiliar.py"
        )

    d = pd.read_parquet(
        ARQUIVO_AUXILIAR
    )

    cd_cvm = _normalizar_cd_cvm(
        cd_cvm
    )

    d = d[
        d["CD_CVM"]
        .astype(str)
        .str.zfill(6)
        .eq(
            cd_cvm
        )
    ].copy()

    ativo = d[
        (
            d["DEMONSTRACAO"]
            == "BPA"
        )
        & (
            d["CD_CONTA"]
            .astype(str)
            .str.strip()
            .eq("1")
        )
    ]

    pl = d[
        (
            d["DEMONSTRACAO"]
            == "BPP"
        )
        & (
            d["DS_CONTA"]
            .map(
                normalizar_descricao
            )
            .eq(
                normalizar_descricao(
                    "Patrimônio Líquido Consolidado"
                )
            )
        )
    ]

    return {
        "AT": (
            float(
                ativo.iloc[0][
                    "VL_CONTA"
                ]
            )
            if len(
                ativo
            ) == 1
            else None
        ),

        "PL": (
            float(
                pl.iloc[0][
                    "VL_CONTA"
                ]
            )
            if len(
                pl
            ) == 1
            else None
        ),
    }


def _componentes_ano(
    cd_cvm: str,
    ano: int,
) -> dict[str, object]:

    bpa = carregar_demonstracao(
        cd_cvm,
        ano,
        "BPA",
    )

    bpp = carregar_demonstracao(
        cd_cvm,
        ano,
        "BPP",
    )

    dre = carregar_demonstracao(
        cd_cvm,
        ano,
        "DRE",
    )

    layout = detectar_layout(
        bpp,
        dre,
    )

    componentes: dict[str, object] = {
        "LAYOUT": (
            layout.codigo
        ),
        "LAYOUT_DESCRICAO": (
            layout.descricao
        ),
        "CODIGO_PL": (
            layout.codigo_pl
        ),
        "CODIGO_LL": (
            layout.codigo_ll
        ),

        "AT": (
            _valor_conta(
                bpa,
                "1",
            )
        ),

        "PL": (
            _valor_conta(
                bpp,
                layout.codigo_pl,
            )
        ),

        "LL": (
            _valor_conta(
                dre,
                layout.codigo_ll,
            )
        ),
    }

    if (
        layout.codigo
        == LAYOUT_PADRAO
    ):

        componentes.update(
            {
                "AC": _valor_conta(
                    bpa,
                    "1.01",
                ),

                "DISP": _valor_conta(
                    bpa,
                    "1.01.01",
                ),

                "APLIC": _valor_conta(
                    bpa,
                    "1.01.02",
                ),

                "CR": _valor_conta(
                    bpa,
                    "1.01.03",
                ),

                "RLP": _valor_conta(
                    bpa,
                    "1.02.01",
                ),

                "INV": _valor_conta(
                    bpa,
                    "1.02.02",
                ),

                "IMOB": _valor_conta(
                    bpa,
                    "1.02.03",
                ),

                "INTANG": _valor_conta(
                    bpa,
                    "1.02.04",
                ),

                "PC": _valor_conta(
                    bpp,
                    "2.01",
                ),

                "EMP_CP": _valor_conta(
                    bpp,
                    "2.01.04",
                ),

                "PNC": _valor_conta(
                    bpp,
                    "2.02",
                ),

                "EMP_LP": _valor_conta(
                    bpp,
                    "2.02.01",
                ),

                "RECEITA": _valor_conta(
                    dre,
                    "3.01",
                ),

                "EBIT": _valor_conta(
                    dre,
                    "3.05",
                ),

                "DESP_FIN": _valor_conta(
                    dre,
                    "3.06.02",
                ),
            }
        )

    else:

        # Não reutilizamos códigos com significados econômicos
        # distintos nos layouts financeiros/securitários.
        componentes.update(
            {
                "AC": None,
                "DISP": None,
                "APLIC": None,
                "CR": None,
                "RLP": None,
                "INV": None,
                "IMOB": None,
                "INTANG": None,
                "PC": None,
                "EMP_CP": None,
                "PNC": None,
                "EMP_LP": None,
                "RECEITA": None,
                "EBIT": None,
                "DESP_FIN": None,
            }
        )

    return componentes


def _layout_objeto_ano(
    cd_cvm: str,
    ano: int,
):
    bpp = carregar_demonstracao(
        cd_cvm,
        ano,
        "BPP",
    )

    dre = carregar_demonstracao(
        cd_cvm,
        ano,
        "DRE",
    )

    return detectar_layout(
        bpp,
        dre,
    )


def calcular_indicadores_ano(
    cd_cvm: str,
    ano: int,
    componentes_anteriores: dict[str, float | None] | None = None,
) -> tuple[
    dict[str, float | None],
    dict[str, object],
]:

    c = _componentes_ano(
        cd_cvm,
        ano,
    )

    layout = _layout_objeto_ano(
        cd_cvm,
        ano,
    )

    anterior = (
        componentes_anteriores
        or {}
    )

    at_medio = _media(
        anterior.get(
            "AT"
        ),
        c["AT"],
    )

    pl_medio_ajustado = (
        _pl_medio_ajustado(
            anterior.get(
                "PL"
            ),
            c["PL"],
            c["LL"],
        )
    )

    if (
        layout.codigo
        == LAYOUT_PADRAO
    ):

        ap = _somar(
            c["INV"],
            c["IMOB"],
            c["INTANG"],
        )

        capital_terceiros = (
            _somar(
                c["PC"],
                c["PNC"],
            )
        )

        passivo_financeiro = (
            _somar(
                c["EMP_CP"],
                c["EMP_LP"],
            )
        )

        ativo_liquido_seco = (
            _somar(
                c["DISP"],
                c["APLIC"],
                c["CR"],
            )
        )

        indicadores = {
            "IPL": _dividir(
                ap,
                c["PL"],
            ),

            "PCT": _dividir(
                capital_terceiros,
                c["PL"],
            ),

            "CE": _dividir(
                c["PC"],
                capital_terceiros,
            ),

            "EFSAT": _dividir(
                passivo_financeiro,
                c["AT"],
            ),

            "LG": _dividir(
                _somar(
                    c["AC"],
                    c["RLP"],
                ),
                capital_terceiros,
            ),

            "LC": _dividir(
                c["AC"],
                c["PC"],
            ),

            "LS": _dividir(
                ativo_liquido_seco,
                c["PC"],
            ),

            "ICJ": _dividir(
                c["EBIT"],
                c["DESP_FIN"],
                absoluto_denominador=True,
            ),

            "GA": _dividir(
                c["RECEITA"],
                at_medio,
            ),

            "RSV": _dividir(
                c["LL"],
                c["RECEITA"],
            ),

            "ROA": _dividir(
                c["LL"],
                at_medio,
            ),

            "ROE": _dividir(
                c["LL"],
                pl_medio_ajustado,
            ),
        }

        componentes_auditaveis = {
            **c,
            "AP": ap,
            "CT": (
                capital_terceiros
            ),
            "PF": (
                passivo_financeiro
            ),
            "ATm": at_medio,
            "PLma": (
                pl_medio_ajustado
            ),
            "AT_inicial": (
                anterior.get(
                    "AT"
                )
            ),
            "PL_inicial": (
                anterior.get(
                    "PL"
                )
            ),
        }

        return (
            indicadores,
            componentes_auditaveis,
        )

    indicadores = {
        codigo: None
        for codigo
        in ORDEM_INDICADORES
    }

    if indicador_aplicavel(
        layout,
        "ROA",
    ):
        indicadores[
            "ROA"
        ] = _dividir(
            c["LL"],
            at_medio,
        )

    if indicador_aplicavel(
        layout,
        "ROE",
    ):
        indicadores[
            "ROE"
        ] = _dividir(
            c["LL"],
            pl_medio_ajustado,
        )

    componentes_auditaveis = {
        **c,
        "AP": None,
        "CT": None,
        "PF": None,
        "ATm": at_medio,
        "PLma": (
            pl_medio_ajustado
        ),
        "AT_inicial": (
            anterior.get(
                "AT"
            )
        ),
        "PL_inicial": (
            anterior.get(
                "PL"
            )
        ),
    }

    return (
        indicadores,
        componentes_auditaveis,
    )


def calcular_indicadores(
    cd_cvm: str,
    anos: list[int] | None = None,
) -> pd.DataFrame:

    cd_cvm = _normalizar_cd_cvm(
        cd_cvm
    )

    disponiveis = anos_disponiveis(
        cd_cvm
    )

    if anos is None:

        anos_usados = (
            disponiveis
        )

    else:

        anos_usados = sorted(
            int(
                ano
            )
            for ano in anos
            if int(
                ano
            )
            in disponiveis
        )

    if not anos_usados:

        return pd.DataFrame()

    primeiro_ano = min(
        anos_usados
    )

    if (
        primeiro_ano
        == min(
            disponiveis
        )
    ):

        auxiliar = (
            _carregar_auxiliar_2022(
                cd_cvm
            )
        )

        componentes_anteriores = {
            "AT": (
                auxiliar[
                    "AT"
                ]
            ),
            "PL": (
                auxiliar[
                    "PL"
                ]
            ),
        }

    else:

        anterior_comp = (
            _componentes_ano(
                cd_cvm,
                primeiro_ano - 1,
            )
        )

        componentes_anteriores = {
            "AT": (
                anterior_comp[
                    "AT"
                ]
            ),
            "PL": (
                anterior_comp[
                    "PL"
                ]
            ),
        }

    linhas = []

    for ano in anos_usados:

        layout = (
            _layout_objeto_ano(
                cd_cvm,
                ano,
            )
        )

        (
            indicadores,
            componentes,
        ) = calcular_indicadores_ano(
            cd_cvm,
            ano,
            componentes_anteriores,
        )

        for codigo in ORDEM_INDICADORES:

            aplicavel = (
                indicador_aplicavel(
                    layout,
                    codigo,
                )
            )

            linhas.append(
                {
                    "CD_CVM": cd_cvm,
                    "ANO": ano,
                    "GRUPO": (
                        GRUPOS[
                            codigo
                        ]
                    ),
                    "INDICADOR": codigo,
                    "UNIDADE": (
                        UNIDADES[
                            codigo
                        ]
                    ),
                    "VALOR": (
                        indicadores[
                            codigo
                        ]
                    ),
                    "FORMULA": (
                        FORMULAS[
                            codigo
                        ]
                    ),
                    "LAYOUT": (
                        layout.codigo
                    ),
                    "LAYOUT_DESCRICAO": (
                        layout.descricao
                    ),
                    "APLICABILIDADE": (
                        "APLICAVEL"
                        if aplicavel
                        else "NAO_APLICAVEL"
                    ),
                    "MOTIVO_NA": (
                        None
                        if aplicavel
                        else (
                            motivo_nao_aplicavel(
                                layout,
                                codigo,
                            )
                        )
                    ),
                }
            )

        componentes_anteriores = {
            "AT": (
                componentes[
                    "AT"
                ]
            ),
            "PL": (
                componentes[
                    "PL"
                ]
            ),
        }

    return pd.DataFrame(
        linhas
    )


def quadro_indicadores(
    cd_cvm: str,
    anos: list[int] | None = None,
) -> pd.DataFrame:

    base = calcular_indicadores(
        cd_cvm,
        anos=anos,
    )

    if base.empty:
        return base

    valores = (
        base.pivot(
            index=[
                "GRUPO",
                "INDICADOR",
                "UNIDADE",
            ],
            columns="ANO",
            values="VALOR",
        )
        .reset_index()
    )

    metadados = (
        base.groupby(
            [
                "GRUPO",
                "INDICADOR",
                "UNIDADE",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            LAYOUT=(
                "LAYOUT",
                lambda s: (
                    " / ".join(
                        sorted(
                            set(
                                str(
                                    valor
                                )
                                for valor
                                in s.dropna()
                            )
                        )
                    )
                ),
            ),
            APLICABILIDADE=(
                "APLICABILIDADE",
                lambda s: (
                    "APLICAVEL"
                    if (
                        s.eq(
                            "APLICAVEL"
                        )
                        .all()
                    )
                    else "NAO_APLICAVEL"
                ),
            ),
            MOTIVO_NA=(
                "MOTIVO_NA",
                lambda s: next(
                    (
                        str(
                            valor
                        )
                        for valor
                        in s
                        if pd.notna(
                            valor
                        )
                        and str(
                            valor
                        ).strip()
                    ),
                    None,
                ),
            ),
        )
    )

    valores = valores.merge(
        metadados,
        on=[
            "GRUPO",
            "INDICADOR",
            "UNIDADE",
        ],
        how="left",
        validate="one_to_one",
    )

    valores[
        "_ORDEM"
    ] = (
        valores[
            "INDICADOR"
        ]
        .map(
            {
                codigo: indice
                for indice, codigo
                in enumerate(
                    ORDEM_INDICADORES
                )
            }
        )
    )

    colunas_base = [
        "GRUPO",
        "INDICADOR",
        "UNIDADE",
    ]

    colunas_anos = sorted(
        [
            coluna
            for coluna
            in valores.columns
            if isinstance(
                coluna,
                int,
            )
        ]
    )

    colunas_meta = [
        "LAYOUT",
        "APLICABILIDADE",
        "MOTIVO_NA",
    ]

    valores = (
        valores.sort_values(
            "_ORDEM"
        )
        [
            colunas_base
            + colunas_anos
            + colunas_meta
        ]
        .reset_index(
            drop=True
        )
    )

    valores.columns.name = None

    return valores


def detalhar_indicador(
    cd_cvm: str,
    ano: int,
    indicador: str,
) -> dict[str, object]:

    indicador = (
        indicador
        .upper()
        .strip()
    )

    if indicador not in FORMULAS:

        raise ValueError(
            "Indicador inválido: "
            f"{indicador}"
        )

    cd_cvm = _normalizar_cd_cvm(
        cd_cvm
    )

    disponiveis = anos_disponiveis(
        cd_cvm
    )

    if ano not in disponiveis:

        raise ValueError(
            f"Ano {ano} não disponível "
            f"para {cd_cvm}."
        )

    layout = (
        _layout_objeto_ano(
            cd_cvm,
            ano,
        )
    )

    if (
        ano
        == min(
            disponiveis
        )
    ):

        aux = (
            _carregar_auxiliar_2022(
                cd_cvm
            )
        )

        anterior = {
            "AT": (
                aux[
                    "AT"
                ]
            ),
            "PL": (
                aux[
                    "PL"
                ]
            ),
        }

    else:

        anterior_comp = (
            _componentes_ano(
                cd_cvm,
                ano - 1,
            )
        )

        anterior = {
            "AT": (
                anterior_comp[
                    "AT"
                ]
            ),
            "PL": (
                anterior_comp[
                    "PL"
                ]
            ),
        }

    valores, componentes = (
        calcular_indicadores_ano(
            cd_cvm,
            ano,
            anterior,
        )
    )

    aplicavel = indicador_aplicavel(
        layout,
        indicador,
    )

    return {
        "CD_CVM": cd_cvm,
        "ANO": ano,
        "INDICADOR": indicador,
        "GRUPO": (
            GRUPOS[
                indicador
            ]
        ),
        "UNIDADE": (
            UNIDADES[
                indicador
            ]
        ),
        "FORMULA": (
            FORMULAS[
                indicador
            ]
        ),
        "RESULTADO": (
            valores[
                indicador
            ]
        ),
        "COMPONENTES": (
            componentes
        ),
        "LAYOUT": (
            layout.codigo
        ),
        "LAYOUT_DESCRICAO": (
            layout.descricao
        ),
        "APLICABILIDADE": (
            "APLICAVEL"
            if aplicavel
            else "NAO_APLICAVEL"
        ),
        "MOTIVO_NA": (
            None
            if aplicavel
            else (
                motivo_nao_aplicavel(
                    layout,
                    indicador,
                )
            )
        ),
    }


def validar_dupont(
    cd_cvm: str,
    anos: list[int] | None = None,
    tolerancia: float = 1e-10,
) -> pd.DataFrame:

    base = calcular_indicadores(
        cd_cvm,
        anos=anos,
    )

    if base.empty:
        return pd.DataFrame()

    pivo = base.pivot(
        index="ANO",
        columns="INDICADOR",
        values="VALOR",
    )

    meta_ano = (
        base.groupby(
            "ANO",
            as_index=True,
        )
        .agg(
            LAYOUT=(
                "LAYOUT",
                "first",
            )
        )
    )

    linhas = []

    for ano, linha in (
        pivo.iterrows()
    ):

        ga = linha.get(
            "GA"
        )

        rsv = linha.get(
            "RSV"
        )

        roa = linha.get(
            "ROA"
        )

        layout = str(
            meta_ano.loc[
                ano,
                "LAYOUT",
            ]
        )

        if (
            layout
            != LAYOUT_PADRAO
        ):

            calculado = None
            diferenca = None
            status = "N/A"

        elif (
            pd.isna(
                ga
            )
            or pd.isna(
                rsv
            )
            or pd.isna(
                roa
            )
        ):

            calculado = None
            diferenca = None
            status = "N/D"

        else:

            calculado = (
                float(
                    ga
                )
                * float(
                    rsv
                )
            )

            diferenca = (
                float(
                    roa
                )
                - calculado
            )

            status = (
                "OK"
                if abs(
                    diferenca
                )
                <= tolerancia
                else "ERRO"
            )

        linhas.append(
            {
                "ANO": int(
                    ano
                ),
                "GA": (
                    None
                    if pd.isna(
                        ga
                    )
                    else float(
                        ga
                    )
                ),
                "RSV": (
                    None
                    if pd.isna(
                        rsv
                    )
                    else float(
                        rsv
                    )
                ),
                "ROA": (
                    None
                    if pd.isna(
                        roa
                    )
                    else float(
                        roa
                    )
                ),
                "GA_X_RSV": (
                    calculado
                ),
                "DIFERENCA": (
                    diferenca
                ),
                "STATUS": (
                    status
                ),
                "LAYOUT": (
                    layout
                ),
            }
        )

    return pd.DataFrame(
        linhas
    )

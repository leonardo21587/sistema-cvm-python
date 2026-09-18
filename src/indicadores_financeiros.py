from __future__ import annotations

"""
Indicadores setoriais — instituições financeiras.

Este módulo é deliberadamente separado de src/indicadores.py para preservar
o motor tradicional já aprovado.

Indicadores implementados nesta primeira camada:
- CAP_CONTABIL: Patrimônio Líquido / Ativo Total
- PF_ATIVO: Passivos Financeiros / Ativo Total
- CRESC_ATIVO: crescimento do Ativo Total
- CRESC_PL: crescimento do Patrimônio Líquido
- CRESC_LL: crescimento do Lucro Líquido com regra de sinal
- RBI_ATIVO_MEDIO: Resultado Bruto da Intermediação / Ativo Médio
- PRETRIB_ATIVO_MEDIO: Resultado antes dos Tributos / Ativo Médio

ROA e ROE NÃO são recalculados aqui. Permanecem no motor tradicional/setorial
já aprovado em src/indicadores.py.
"""

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from config.settings import PROCESSED_DIR  # noqa: E402
from src.banco import (  # noqa: E402
    anos_disponiveis,
    carregar_demonstracao,
)
from src.layouts_cvm import (  # noqa: E402
    LAYOUT_FINANCEIRA,
    detectar_layout,
    normalizar_descricao,
)


ARQUIVO_AUXILIAR = (
    PROCESSED_DIR
    / "saldos_auxiliares_2022.parquet"
)


INDICADORES_FINANCEIROS = [
    "CAP_CONTABIL",
    "PF_ATIVO",
    "CRESC_ATIVO",
    "CRESC_PL",
    "CRESC_LL",
    "RBI_ATIVO_MEDIO",
    "PRETRIB_ATIVO_MEDIO",
]


NOMES = {
    "CAP_CONTABIL": "Capitalização Contábil",
    "PF_ATIVO": "Passivos Financeiros / Ativo Total",
    "CRESC_ATIVO": "Crescimento do Ativo Total",
    "CRESC_PL": "Crescimento do Patrimônio Líquido",
    "CRESC_LL": "Crescimento do Lucro Líquido",
    "RBI_ATIVO_MEDIO": (
        "Resultado Bruto da Intermediação / Ativo Médio"
    ),
    "PRETRIB_ATIVO_MEDIO": (
        "Resultado Pré-Tributos / Ativo Médio"
    ),
}


GRUPOS = {
    "CAP_CONTABIL": "Capitalização e Funding",
    "PF_ATIVO": "Capitalização e Funding",
    "CRESC_ATIVO": "Crescimento",
    "CRESC_PL": "Crescimento",
    "CRESC_LL": "Crescimento",
    "RBI_ATIVO_MEDIO": "Intermediação e Rentabilidade",
    "PRETRIB_ATIVO_MEDIO": "Intermediação e Rentabilidade",
}


FORMULAS = {
    "CAP_CONTABIL": "Patrimônio Líquido Consolidado / Ativo Total",
    "PF_ATIVO": (
        "Soma dos componentes top-level de Passivos Financeiros "
        "/ Ativo Total"
    ),
    "CRESC_ATIVO": "Ativo Total_t / Ativo Total_t-1 - 1",
    "CRESC_PL": (
        "Patrimônio Líquido_t / Patrimônio Líquido_t-1 - 1"
    ),
    "CRESC_LL": (
        "Lucro Líquido_t / Lucro Líquido_t-1 - 1, "
        "somente quando LL_t-1 > 0 e LL_t >= 0"
    ),
    "RBI_ATIVO_MEDIO": (
        "Resultado Bruto da Intermediação "
        "/ [(Ativo Total_t-1 + Ativo Total_t) / 2]"
    ),
    "PRETRIB_ATIVO_MEDIO": (
        "Resultado antes dos Tributos sobre o Lucro "
        "/ [(Ativo Total_t-1 + Ativo Total_t) / 2]"
    ),
}


UNIDADES = {
    codigo: "%"
    for codigo in INDICADORES_FINANCEIROS
}


DESC_PL = {
    normalizar_descricao(
        "Patrimônio Líquido Consolidado"
    ),
}


DESC_LL = {
    normalizar_descricao(
        "Lucro/Prejuízo Consolidado do Período"
    ),
    normalizar_descricao(
        "Lucro ou Prejuízo Líquido Consolidado do Período"
    ),
}


DESC_RBI = {
    normalizar_descricao(
        "Resultado Bruto de Intermediação Financeira"
    ),
    normalizar_descricao(
        "Resultado Bruto Intermediação Financeira"
    ),
}


DESC_PRETRIB = {
    normalizar_descricao(
        "Resultado antes dos Tributos sobre o Lucro"
    ),
    normalizar_descricao(
        "Resultado Antes dos Tributos sobre o Lucro"
    ),
}


def _normalizar_cd_cvm(
    cd_cvm: str,
) -> str:
    return (
        str(cd_cvm)
        .strip()
        .zfill(6)
    )


def _numero(
    valor,
) -> float | None:
    if valor is None:
        return None

    if pd.isna(valor):
        return None

    return float(valor)


def _dividir(
    numerador: float | None,
    denominador: float | None,
) -> float | None:
    numerador = _numero(
        numerador
    )
    denominador = _numero(
        denominador
    )

    if (
        numerador is None
        or denominador is None
        or denominador == 0
    ):
        return None

    return (
        numerador
        / denominador
    )


def _media(
    inicial: float | None,
    final: float | None,
) -> float | None:
    inicial = _numero(
        inicial
    )
    final = _numero(
        final
    )

    if (
        inicial is None
        or final is None
    ):
        return None

    return (
        inicial
        + final
    ) / 2.0


def _crescimento(
    atual: float | None,
    anterior: float | None,
) -> float | None:
    atual = _numero(
        atual
    )
    anterior = _numero(
        anterior
    )

    if (
        atual is None
        or anterior is None
        or anterior == 0
    ):
        return None

    return (
        atual
        / anterior
        - 1.0
    )


def _valor_unico_codigo(
    df: pd.DataFrame,
    codigo: str,
) -> float | None:
    if (
        df is None
        or df.empty
    ):
        return None

    linhas = df[
        df["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq(
            str(codigo)
        )
    ]

    if len(linhas) != 1:
        return None

    return _numero(
        linhas.iloc[0][
            "VL_CONTA"
        ]
    )


def _valor_unico_descricao(
    df: pd.DataFrame,
    descricoes_normalizadas: set[str],
) -> float | None:
    if (
        df is None
        or df.empty
        or "DS_CONTA" not in df.columns
    ):
        return None

    mascara = (
        df["DS_CONTA"]
        .map(
            normalizar_descricao
        )
        .isin(
            descricoes_normalizadas
        )
    )

    linhas = df[
        mascara
    ]

    if len(linhas) != 1:
        return None

    return _numero(
        linhas.iloc[0][
            "VL_CONTA"
        ]
    )


def _componentes_passivos_financeiros(
    bpp: pd.DataFrame,
) -> tuple[
    float | None,
    tuple[str, ...],
]:
    if (
        bpp is None
        or bpp.empty
    ):
        return (
            None,
            tuple(),
        )

    d = bpp.copy()

    descricao = (
        d["DS_CONTA"]
        .map(
            normalizar_descricao
        )
    )

    mascara = (
        d["CD_CONTA"]
        .astype(str)
        .str.strip()
        .str.match(
            r"^2\.\d{2}$",
            na=False,
        )
        & descricao.str.contains(
            "PASSIVOS FINANCEIROS",
            na=False,
        )
    )

    componentes = (
        d.loc[
            mascara,
            [
                "CD_CONTA",
                "VL_CONTA",
            ],
        ]
        .copy()
    )

    if componentes.empty:
        return (
            None,
            tuple(),
        )

    if componentes[
        "VL_CONTA"
    ].isna().any():
        return (
            None,
            tuple(
                componentes[
                    "CD_CONTA"
                ]
                .astype(str)
                .sort_values()
            ),
        )

    codigos = tuple(
        componentes[
            "CD_CONTA"
        ]
        .astype(str)
        .sort_values()
    )

    valor = float(
        componentes[
            "VL_CONTA"
        ].sum()
    )

    return (
        valor,
        codigos,
    )


def _carregar_componentes_ano(
    cd_cvm: str,
    ano: int,
) -> dict[str, object]:
    cd_cvm = _normalizar_cd_cvm(
        cd_cvm
    )
    ano = int(
        ano
    )

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

    if (
        layout.codigo
        != LAYOUT_FINANCEIRA
    ):
        return {
            "LAYOUT": layout.codigo,
            "AT": None,
            "PL": None,
            "LL": None,
            "PF": None,
            "PF_CODIGOS": tuple(),
            "RBI": None,
            "PRETRIB": None,
        }

    pf, pf_codigos = (
        _componentes_passivos_financeiros(
            bpp
        )
    )

    return {
        "LAYOUT": layout.codigo,
        "CODIGO_PL": layout.codigo_pl,
        "CODIGO_LL": layout.codigo_ll,
        "AT": _valor_unico_codigo(
            bpa,
            "1",
        ),
        "PL": _valor_unico_descricao(
            bpp,
            DESC_PL,
        ),
        "LL": _valor_unico_descricao(
            dre,
            DESC_LL,
        ),
        "PF": pf,
        "PF_CODIGOS": pf_codigos,
        "RBI": _valor_unico_descricao(
            dre,
            DESC_RBI,
        ),
        "PRETRIB": _valor_unico_descricao(
            dre,
            DESC_PRETRIB,
        ),
    }


def _carregar_auxiliar_2022(
    cd_cvm: str,
) -> dict[str, float | None]:
    if not ARQUIVO_AUXILIAR.exists():
        raise FileNotFoundError(
            "Arquivo auxiliar não encontrado: "
            f"{ARQUIVO_AUXILIAR}"
        )

    d = pd.read_parquet(
        ARQUIVO_AUXILIAR
    ).copy()

    cd_cvm = _normalizar_cd_cvm(
        cd_cvm
    )

    d["CD_CVM"] = (
        d["CD_CVM"]
        .astype(str)
        .str.zfill(6)
    )

    d = d[
        d["CD_CVM"]
        .eq(
            cd_cvm
        )
    ].copy()

    ativo = d[
        d["DEMONSTRACAO"]
        .astype(str)
        .str.upper()
        .eq("BPA")
        & d["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq("1")
    ]

    pl = d[
        d["DEMONSTRACAO"]
        .astype(str)
        .str.upper()
        .eq("BPP")
        & d["DS_CONTA"]
        .map(
            normalizar_descricao
        )
        .eq(
            normalizar_descricao(
                "Patrimônio Líquido Consolidado"
            )
        )
    ]

    return {
        "AT": (
            _numero(
                ativo.iloc[0][
                    "VL_CONTA"
                ]
            )
            if len(ativo) == 1
            else None
        ),
        "PL": (
            _numero(
                pl.iloc[0][
                    "VL_CONTA"
                ]
            )
            if len(pl) == 1
            else None
        ),
    }


def _status_crescimento_ll(
    atual: float | None,
    anterior: float | None,
) -> tuple[
    float | None,
    str,
    str | None,
]:
    atual = _numero(
        atual
    )
    anterior = _numero(
        anterior
    )

    if anterior is None:
        return (
            None,
            "N/D",
            "Lucro Líquido do exercício anterior indisponível.",
        )

    if atual is None:
        return (
            None,
            "N/D",
            "Lucro Líquido do exercício atual indisponível.",
        )

    if anterior == 0:
        return (
            None,
            "N/A",
            (
                "Crescimento percentual do Lucro Líquido "
                "não é interpretável com base anterior igual a zero."
            ),
        )

    if anterior < 0 and atual > 0:
        return (
            None,
            "N/A",
            (
                "Houve transição de prejuízo para lucro; "
                "a taxa percentual convencional não é interpretável."
            ),
        )

    if anterior > 0 and atual < 0:
        return (
            None,
            "N/A",
            (
                "Houve transição de lucro para prejuízo; "
                "a taxa percentual convencional não é interpretável."
            ),
        )

    if anterior < 0:
        return (
            None,
            "N/A",
            (
                "A base do Lucro Líquido é negativa; "
                "a taxa percentual convencional não é usada."
            ),
        )

    valor = (
        atual
        / anterior
        - 1.0
    )

    return (
        valor,
        "OK",
        None,
    )


def _linha(
    *,
    cd_cvm: str,
    ano: int,
    codigo: str,
    valor: float | None,
    status: str,
    motivo: str | None,
    layout: str,
) -> dict[str, object]:
    return {
        "CD_CVM": cd_cvm,
        "ANO": int(ano),
        "GRUPO": GRUPOS[
            codigo
        ],
        "INDICADOR": codigo,
        "NOME": NOMES[
            codigo
        ],
        "UNIDADE": UNIDADES[
            codigo
        ],
        "VALOR": valor,
        "FORMULA": FORMULAS[
            codigo
        ],
        "STATUS": status,
        "MOTIVO": motivo,
        "LAYOUT": layout,
    }


def calcular_indicadores_financeiros(
    cd_cvm: str,
    anos: list[int] | None = None,
) -> pd.DataFrame:
    """
    Calcula somente a camada setorial FINANCEIRA.

    Regras:
    - não calcula para anos cujo layout não seja FINANCEIRA;
    - crescimento começa em 2024, pois 2023 é o exercício-base
      do painel 2023-2025;
    - RBI/Ativo Médio e Pré-Tributos/Ativo Médio podem usar
      Ativo Total auxiliar de 2022 para 2023;
    - ausência de dado necessário gera N/D;
    - crescimento do LL com base negativa, base zero ou mudança
      de sinal gera N/A metodológico.
    """
    cd_cvm = _normalizar_cd_cvm(
        cd_cvm
    )

    disponiveis = anos_disponiveis(
        cd_cvm
    )

    if anos is None:
        anos_usados = sorted(
            int(a)
            for a in disponiveis
        )
    else:
        anos_usados = sorted(
            {
                int(a)
                for a in anos
                if int(a) in disponiveis
            }
        )

    if not anos_usados:
        return pd.DataFrame()

    componentes_por_ano: dict[
        int,
        dict[str, object],
    ] = {}

    for ano in anos_usados:
        componentes_por_ano[
            ano
        ] = _carregar_componentes_ano(
            cd_cvm,
            ano,
        )

    auxiliar = (
        _carregar_auxiliar_2022(
            cd_cvm
        )
        if 2023 in anos_usados
        else {
            "AT": None,
            "PL": None,
        }
    )

    linhas: list[
        dict[str, object]
    ] = []

    for ano in anos_usados:
        c = componentes_por_ano[
            ano
        ]

        if (
            c["LAYOUT"]
            != LAYOUT_FINANCEIRA
        ):
            continue

        if ano == 2023:
            anterior = {
                "AT": auxiliar.get(
                    "AT"
                ),
                "PL": auxiliar.get(
                    "PL"
                ),
                "LL": None,
            }
        else:
            anterior = (
                componentes_por_ano.get(
                    ano - 1,
                    {}
                )
            )

        at = _numero(
            c.get(
                "AT"
            )
        )
        pl = _numero(
            c.get(
                "PL"
            )
        )
        ll = _numero(
            c.get(
                "LL"
            )
        )
        pf = _numero(
            c.get(
                "PF"
            )
        )
        rbi = _numero(
            c.get(
                "RBI"
            )
        )
        pretrib = _numero(
            c.get(
                "PRETRIB"
            )
        )

        at_anterior = _numero(
            anterior.get(
                "AT"
            )
        )
        pl_anterior = _numero(
            anterior.get(
                "PL"
            )
        )
        ll_anterior = _numero(
            anterior.get(
                "LL"
            )
        )

        at_medio = _media(
            at_anterior,
            at,
        )

        # ----------------------------------------------------
        # Capitalização Contábil
        # ----------------------------------------------------
        cap = _dividir(
            pl,
            at,
        )

        linhas.append(
            _linha(
                cd_cvm=cd_cvm,
                ano=ano,
                codigo="CAP_CONTABIL",
                valor=cap,
                status=(
                    "OK"
                    if cap is not None
                    else "N/D"
                ),
                motivo=(
                    None
                    if cap is not None
                    else (
                        "Ativo Total ausente ou igual a zero, "
                        "ou Patrimônio Líquido indisponível."
                    )
                ),
                layout=str(
                    c["LAYOUT"]
                ),
            )
        )

        # ----------------------------------------------------
        # Passivos Financeiros / Ativo
        # ----------------------------------------------------
        pf_at = _dividir(
            pf,
            at,
        )

        linhas.append(
            _linha(
                cd_cvm=cd_cvm,
                ano=ano,
                codigo="PF_ATIVO",
                valor=pf_at,
                status=(
                    "OK"
                    if pf_at is not None
                    else "N/D"
                ),
                motivo=(
                    None
                    if pf_at is not None
                    else (
                        "Ativo Total ausente ou igual a zero, "
                        "ou componentes de Passivos Financeiros indisponíveis."
                    )
                ),
                layout=str(
                    c["LAYOUT"]
                ),
            )
        )

        # ----------------------------------------------------
        # Crescimentos — apenas 2024/2025 no painel atual
        # ----------------------------------------------------
        if ano <= 2023:
            cresc_at = None
            status_cresc_at = "N/D"
            motivo_cresc_at = (
                "2023 é o exercício-base do painel; "
                "o crescimento começa em 2024."
            )
        else:
            cresc_at = _crescimento(
                at,
                at_anterior,
            )
            status_cresc_at = (
                "OK"
                if cresc_at is not None
                else "N/D"
            )
            motivo_cresc_at = (
                None
                if cresc_at is not None
                else (
                    "Ativo Total do exercício anterior "
                    "ausente ou igual a zero."
                )
            )

        linhas.append(
            _linha(
                cd_cvm=cd_cvm,
                ano=ano,
                codigo="CRESC_ATIVO",
                valor=cresc_at,
                status=status_cresc_at,
                motivo=motivo_cresc_at,
                layout=str(
                    c["LAYOUT"]
                ),
            )
        )

        if ano <= 2023:
            cresc_pl = None
            status_cresc_pl = "N/D"
            motivo_cresc_pl = (
                "2023 é o exercício-base do painel; "
                "o crescimento começa em 2024."
            )
        else:
            cresc_pl = _crescimento(
                pl,
                pl_anterior,
            )
            status_cresc_pl = (
                "OK"
                if cresc_pl is not None
                else "N/D"
            )
            motivo_cresc_pl = (
                None
                if cresc_pl is not None
                else (
                    "Patrimônio Líquido do exercício anterior "
                    "ausente ou igual a zero."
                )
            )

        linhas.append(
            _linha(
                cd_cvm=cd_cvm,
                ano=ano,
                codigo="CRESC_PL",
                valor=cresc_pl,
                status=status_cresc_pl,
                motivo=motivo_cresc_pl,
                layout=str(
                    c["LAYOUT"]
                ),
            )
        )

        if ano <= 2023:
            cresc_ll = None
            status_cresc_ll = "N/D"
            motivo_cresc_ll = (
                "2023 é o exercício-base do painel; "
                "o crescimento começa em 2024."
            )
        else:
            (
                cresc_ll,
                status_cresc_ll,
                motivo_cresc_ll,
            ) = _status_crescimento_ll(
                ll,
                ll_anterior,
            )

        linhas.append(
            _linha(
                cd_cvm=cd_cvm,
                ano=ano,
                codigo="CRESC_LL",
                valor=cresc_ll,
                status=status_cresc_ll,
                motivo=motivo_cresc_ll,
                layout=str(
                    c["LAYOUT"]
                ),
            )
        )

        # ----------------------------------------------------
        # RBI / Ativo Médio
        # ----------------------------------------------------
        rbi_atm = _dividir(
            rbi,
            at_medio,
        )

        linhas.append(
            _linha(
                cd_cvm=cd_cvm,
                ano=ano,
                codigo="RBI_ATIVO_MEDIO",
                valor=rbi_atm,
                status=(
                    "OK"
                    if rbi_atm is not None
                    else "N/D"
                ),
                motivo=(
                    None
                    if rbi_atm is not None
                    else (
                        "Resultado Bruto da Intermediação ou "
                        "Ativo Médio indisponível."
                    )
                ),
                layout=str(
                    c["LAYOUT"]
                ),
            )
        )

        # ----------------------------------------------------
        # Resultado Pré-Tributos / Ativo Médio
        # ----------------------------------------------------
        pretrib_atm = _dividir(
            pretrib,
            at_medio,
        )

        linhas.append(
            _linha(
                cd_cvm=cd_cvm,
                ano=ano,
                codigo="PRETRIB_ATIVO_MEDIO",
                valor=pretrib_atm,
                status=(
                    "OK"
                    if pretrib_atm is not None
                    else "N/D"
                ),
                motivo=(
                    None
                    if pretrib_atm is not None
                    else (
                        "Resultado antes dos Tributos ou "
                        "Ativo Médio indisponível."
                    )
                ),
                layout=str(
                    c["LAYOUT"]
                ),
            )
        )

    return pd.DataFrame(
        linhas
    )


def quadro_indicadores_financeiros(
    cd_cvm: str,
    anos: list[int] | None = None,
) -> pd.DataFrame:
    """
    Retorna uma linha por indicador e uma coluna por ano.

    Mantém STATUS/MOTIVO fora do pivot; para auditoria detalhada,
    usar calcular_indicadores_financeiros().
    """
    dados = calcular_indicadores_financeiros(
        cd_cvm,
        anos,
    )

    if dados.empty:
        return pd.DataFrame()

    valores = (
        dados.pivot(
            index=[
                "GRUPO",
                "INDICADOR",
                "NOME",
                "UNIDADE",
                "FORMULA",
            ],
            columns="ANO",
            values="VALOR",
        )
        .reset_index()
    )

    ordem = {
        codigo: i
        for i, codigo
        in enumerate(
            INDICADORES_FINANCEIROS
        )
    }

    valores["_ORDEM"] = (
        valores["INDICADOR"]
        .map(
            ordem
        )
    )

    valores = (
        valores.sort_values(
            "_ORDEM"
        )
        .drop(
            columns="_ORDEM"
        )
        .reset_index(
            drop=True
        )
    )

    return valores

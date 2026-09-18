from __future__ import annotations

"""
SISTEMA CVM — ETAPA A.3
Diagnóstico econômico/estatístico dos indicadores candidatos FINANCEIRA.

Objetivo:
- SOMENTE LEITURA.
- Não altera app.py, src/indicadores.py, ETL ou DuckDB.
- Valida denominadores, zeros, sinais, transições, outliers e cobertura do ano auxiliar 2022.
- Não implementa indicadores no sistema.
"""

from pathlib import Path
import sys
import math

import numpy as np
import pandas as pd


ARQUIVO = Path(__file__).resolve()
ROOT_DIR = ARQUIVO.parents[1] if ARQUIVO.parent.name.lower() == "tests" else ARQUIVO.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar  # noqa: E402
from src.layouts_cvm import (  # noqa: E402
    LAYOUT_FINANCEIRA,
    detectar_layout,
    normalizar_descricao,
)


ANOS = [2023, 2024, 2025]

AUX_2022 = (
    ROOT_DIR
    / "data"
    / "processed"
    / "saldos_auxiliares_2022.parquet"
)

SAIDA_DIR = (
    ROOT_DIR
    / "data"
    / "auditoria"
    / "financeiras_etapa_a3"
)

SAIDA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# UTILITÁRIOS
# ============================================================

def _normalizar_cd_cvm(serie: pd.Series) -> pd.Series:
    return (
        serie.astype("string")
        .fillna("")
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .str.zfill(6)
    )


def _is_conta_fixa(serie: pd.Series) -> pd.Series:
    s = (
        serie.astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )

    return s.isin(
        {
            "S",
            "SIM",
            "1",
            "TRUE",
            "T",
        }
    )


def _safe_ratio(
    numerador: float | int | None,
    denominador: float | int | None,
) -> float:
    if numerador is None or denominador is None:
        return np.nan

    if pd.isna(numerador) or pd.isna(denominador):
        return np.nan

    if float(denominador) == 0:
        return np.nan

    return float(numerador) / float(denominador)


def _safe_growth(
    atual: float | int | None,
    anterior: float | int | None,
) -> float:
    if atual is None or anterior is None:
        return np.nan

    if pd.isna(atual) or pd.isna(anterior):
        return np.nan

    if float(anterior) == 0:
        return np.nan

    return (
        float(atual)
        / float(anterior)
        - 1.0
    )


def _ll_growth_status(
    atual: float | int | None,
    anterior: float | int | None,
) -> tuple[str, float]:
    if (
        atual is None
        or anterior is None
        or pd.isna(atual)
        or pd.isna(anterior)
    ):
        return "SEM_BASE_COMPARAVEL", np.nan

    atual = float(atual)
    anterior = float(anterior)

    if anterior == 0:
        return "BASE_ZERO", np.nan

    if anterior > 0 and atual >= 0:
        return (
            "LUCRO_PARA_LUCRO",
            atual / anterior - 1.0,
        )

    if anterior > 0 and atual < 0:
        return "LUCRO_PARA_PREJUIZO", np.nan

    if anterior < 0 and atual > 0:
        return "PREJUIZO_PARA_LUCRO", np.nan

    if anterior < 0 and atual <= 0:
        return "PREJUIZO_PARA_PREJUIZO", np.nan

    return "CASO_NAO_TRATADO", np.nan


def _isclose(
    a: float | int | None,
    b: float | int | None,
    *,
    rtol: float = 1e-8,
    atol: float = 1e-6,
) -> bool:
    if a is None or b is None:
        return False

    if pd.isna(a) or pd.isna(b):
        return False

    return bool(
        np.isclose(
            float(a),
            float(b),
            rtol=rtol,
            atol=atol,
        )
    )


# ============================================================
# BASE DFP
# ============================================================

def carregar_dfp() -> pd.DataFrame:
    con = conectar(read_only=True)

    try:
        df = con.execute(
            """
            SELECT
                CD_CVM,
                DENOM_CIA,
                CNPJ_CIA,
                ANO,
                DEMONSTRACAO,
                CD_CONTA,
                DS_CONTA,
                ST_CONTA_FIXA,
                VL_CONTA
            FROM dfp
            WHERE ANO BETWEEN 2023 AND 2025
              AND DEMONSTRACAO IN ('BPA', 'BPP', 'DRE')
            """
        ).fetchdf()

    finally:
        con.close()

    df["CD_CVM"] = _normalizar_cd_cvm(
        df["CD_CVM"]
    )

    df["ANO"] = pd.to_numeric(
        df["ANO"],
        errors="coerce",
    ).astype("Int64")

    df["DEMONSTRACAO"] = (
        df["DEMONSTRACAO"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    df["CD_CONTA"] = (
        df["CD_CONTA"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    df["DS_CONTA"] = (
        df["DS_CONTA"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    df["DS_NORM"] = df["DS_CONTA"].map(
        normalizar_descricao
    )

    df["CONTA_FIXA"] = _is_conta_fixa(
        df["ST_CONTA_FIXA"]
    )

    df["VL_CONTA"] = pd.to_numeric(
        df["VL_CONTA"],
        errors="coerce",
    )

    return df


def identificar_pares_financeiros(
    df: pd.DataFrame,
) -> pd.DataFrame:
    linhas = []

    for (cd_cvm, ano), g in df.groupby(
        ["CD_CVM", "ANO"],
        sort=True,
    ):
        bpp = g[
            g["DEMONSTRACAO"].eq("BPP")
        ][
            ["CD_CONTA", "DS_CONTA"]
        ].copy()

        dre = g[
            g["DEMONSTRACAO"].eq("DRE")
        ][
            ["CD_CONTA", "DS_CONTA"]
        ].copy()

        layout = detectar_layout(
            bpp,
            dre,
        )

        if layout.codigo != LAYOUT_FINANCEIRA:
            continue

        nome = (
            g["DENOM_CIA"]
            .dropna()
            .astype(str)
            .iloc[0]
        )

        assinatura = (
            "FIN_207_311"
            if (
                layout.codigo_pl == "2.07"
                and layout.codigo_ll == "3.11"
            )
            else "FIN_208_309"
            if (
                layout.codigo_pl == "2.08"
                and layout.codigo_ll == "3.09"
            )
            else "FIN_OUTRA"
        )

        linhas.append(
            {
                "CD_CVM": cd_cvm,
                "DENOM_CIA": nome,
                "ANO": int(ano),
                "ASSINATURA": assinatura,
                "CODIGO_PL": layout.codigo_pl,
                "CODIGO_LL": layout.codigo_ll,
            }
        )

    return (
        pd.DataFrame(linhas)
        .sort_values(
            ["CD_CVM", "ANO"]
        )
        .reset_index(drop=True)
    )


# ============================================================
# EXTRAÇÃO DAS CONTAS
# ============================================================

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

DESC_RECEITA_INTER = {
    normalizar_descricao(
        "Receitas de Intermediação Financeira"
    ),
    normalizar_descricao(
        "Receitas da Intermediação Financeira"
    ),
}

DESC_RESULTADO_ANTES_TRIB = {
    normalizar_descricao(
        "Resultado antes dos Tributos sobre o Lucro"
    ),
}


def _valor_exato(
    d: pd.DataFrame,
    *,
    demonstracao: str,
    codigo: str | None = None,
    descricoes_norm: set[str] | None = None,
) -> float:
    x = d[
        d["DEMONSTRACAO"].eq(
            demonstracao
        )
    ].copy()

    if codigo is not None:
        x = x[
            x["CD_CONTA"].eq(
                codigo
            )
        ]

    if descricoes_norm is not None:
        x = x[
            x["DS_NORM"].isin(
                descricoes_norm
            )
        ]

    if len(x) != 1:
        return np.nan

    return float(
        x.iloc[0]["VL_CONTA"]
    )


def extrair_financeiras(
    df: pd.DataFrame,
    pares: pd.DataFrame,
) -> pd.DataFrame:
    linhas = []

    for info in pares.itertuples(
        index=False
    ):
        d = df[
            df["CD_CVM"].eq(
                info.CD_CVM
            )
            & df["ANO"].eq(
                info.ANO
            )
            & df["CONTA_FIXA"]
        ].copy()

        ativo = _valor_exato(
            d,
            demonstracao="BPA",
            codigo="1",
        )

        pl = _valor_exato(
            d,
            demonstracao="BPP",
            descricoes_norm=DESC_PL,
        )

        ll = _valor_exato(
            d,
            demonstracao="DRE",
            descricoes_norm=DESC_LL,
        )

        receita = _valor_exato(
            d,
            demonstracao="DRE",
            codigo="3.01",
            descricoes_norm=DESC_RECEITA_INTER,
        )

        rbi = _valor_exato(
            d,
            demonstracao="DRE",
            codigo="3.03",
            descricoes_norm=DESC_RBI,
        )

        resultado_antes = _valor_exato(
            d,
            demonstracao="DRE",
            codigo="3.05",
            descricoes_norm=DESC_RESULTADO_ANTES_TRIB,
        )

        bpp = d[
            d["DEMONSTRACAO"].eq("BPP")
        ].copy()

        componentes_pf = bpp[
            bpp["CD_CONTA"].str.match(
                r"^2\.\d{2}$",
                na=False,
            )
            & bpp["DS_NORM"].str.contains(
                "PASSIVOS FINANCEIROS",
                na=False,
            )
        ].copy()

        passivos_financeiros = (
            float(
                componentes_pf[
                    "VL_CONTA"
                ].sum()
            )
            if not componentes_pf.empty
            else np.nan
        )

        linhas.append(
            {
                "CD_CVM": info.CD_CVM,
                "DENOM_CIA": info.DENOM_CIA,
                "ANO": int(info.ANO),
                "ASSINATURA": info.ASSINATURA,
                "ATIVO_TOTAL": ativo,
                "PL_CONSOLIDADO": pl,
                "LUCRO_LIQUIDO": ll,
                "RECEITA_INTERMEDIACAO": receita,
                "RBI": rbi,
                "RESULTADO_ANTES_TRIBUTOS": resultado_antes,
                "PASSIVOS_FINANCEIROS": passivos_financeiros,
                "N_COMPONENTES_PF": len(
                    componentes_pf
                ),
            }
        )

    return pd.DataFrame(linhas)


# ============================================================
# SALDOS AUXILIARES 2022
# ============================================================

def carregar_auxiliar_2022() -> pd.DataFrame:
    if not AUX_2022.exists():
        raise FileNotFoundError(
            "Arquivo de saldos auxiliares 2022 não encontrado: "
            f"{AUX_2022}"
        )

    aux = pd.read_parquet(
        AUX_2022
    ).copy()

    aux["CD_CVM"] = _normalizar_cd_cvm(
        aux["CD_CVM"]
    )

    aux["DEMONSTRACAO"] = (
        aux["DEMONSTRACAO"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    aux["CD_CONTA"] = (
        aux["CD_CONTA"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    aux["DS_NORM"] = (
        aux["DS_CONTA"]
        .map(
            normalizar_descricao
        )
    )

    aux["VL_CONTA"] = pd.to_numeric(
        aux["VL_CONTA"],
        errors="coerce",
    )

    return aux


def mapear_auxiliar(
    aux: pd.DataFrame,
) -> tuple[dict[str, float], dict[str, float]]:
    at = aux[
        aux["DEMONSTRACAO"].eq("BPA")
        & aux["CD_CONTA"].eq("1")
    ].copy()

    pl = aux[
        aux["DEMONSTRACAO"].eq("BPP")
        & aux["DS_NORM"].eq(
            normalizar_descricao(
                "Patrimônio Líquido Consolidado"
            )
        )
    ].copy()

    at_map = {
        str(r.CD_CVM): float(r.VL_CONTA)
        for r in at.itertuples(index=False)
    }

    pl_map = {
        str(r.CD_CVM): float(r.VL_CONTA)
        for r in pl.itertuples(index=False)
    }

    return at_map, pl_map


# ============================================================
# MÉTRICAS DIAGNÓSTICAS
# ============================================================

def construir_metricas(
    base: pd.DataFrame,
    at_2022: dict[str, float],
    pl_2022: dict[str, float],
) -> pd.DataFrame:
    lookup = {
        (
            str(r.CD_CVM),
            int(r.ANO),
        ): r
        for r in base.itertuples(
            index=False
        )
    }

    linhas = []

    for r in base.itertuples(
        index=False
    ):
        ano = int(r.ANO)
        cd = str(r.CD_CVM)

        if ano == 2023:
            ativo_ant = at_2022.get(
                cd,
                np.nan,
            )
            pl_ant = pl_2022.get(
                cd,
                np.nan,
            )
            ll_ant = np.nan

        else:
            ant = lookup.get(
                (
                    cd,
                    ano - 1,
                )
            )

            ativo_ant = (
                ant.ATIVO_TOTAL
                if ant is not None
                else np.nan
            )

            pl_ant = (
                ant.PL_CONSOLIDADO
                if ant is not None
                else np.nan
            )

            ll_ant = (
                ant.LUCRO_LIQUIDO
                if ant is not None
                else np.nan
            )

        ativo_medio = (
            (
                float(ativo_ant)
                + float(r.ATIVO_TOTAL)
            )
            / 2.0
            if (
                not pd.isna(ativo_ant)
                and not pd.isna(r.ATIVO_TOTAL)
            )
            else np.nan
        )

        pl_medio = (
            (
                float(pl_ant)
                + float(r.PL_CONSOLIDADO)
            )
            / 2.0
            if (
                not pd.isna(pl_ant)
                and not pd.isna(r.PL_CONSOLIDADO)
            )
            else np.nan
        )

        status_ll, cresc_ll = (
            _ll_growth_status(
                r.LUCRO_LIQUIDO,
                ll_ant,
            )
            if ano > 2023
            else (
                "SEM_BASE_2022_LL",
                np.nan,
            )
        )

        linhas.append(
            {
                "CD_CVM": cd,
                "DENOM_CIA": r.DENOM_CIA,
                "ANO": ano,
                "ASSINATURA": r.ASSINATURA,

                "ATIVO_TOTAL": r.ATIVO_TOTAL,
                "ATIVO_ANTERIOR": ativo_ant,
                "ATIVO_MEDIO": ativo_medio,

                "PL_CONSOLIDADO": r.PL_CONSOLIDADO,
                "PL_ANTERIOR": pl_ant,
                "PL_MEDIO": pl_medio,

                "LUCRO_LIQUIDO": r.LUCRO_LIQUIDO,
                "LL_ANTERIOR": ll_ant,

                "PASSIVOS_FINANCEIROS": r.PASSIVOS_FINANCEIROS,
                "RBI": r.RBI,
                "RECEITA_INTERMEDIACAO": r.RECEITA_INTERMEDIACAO,
                "RESULTADO_ANTES_TRIBUTOS": r.RESULTADO_ANTES_TRIBUTOS,

                "CAPITALIZACAO_CONTABIL": _safe_ratio(
                    r.PL_CONSOLIDADO,
                    r.ATIVO_TOTAL,
                ),

                "PASSIVOS_FINANCEIROS_ATIVO": _safe_ratio(
                    r.PASSIVOS_FINANCEIROS,
                    r.ATIVO_TOTAL,
                ),

                "RBI_ATIVO_MEDIO": _safe_ratio(
                    r.RBI,
                    ativo_medio,
                ),

                "RBI_RECEITA_INTERMEDIACAO": _safe_ratio(
                    r.RBI,
                    r.RECEITA_INTERMEDIACAO,
                ),

                "RESULTADO_PRE_TRIB_ATIVO_MEDIO": _safe_ratio(
                    r.RESULTADO_ANTES_TRIBUTOS,
                    ativo_medio,
                ),

                "CRESCIMENTO_ATIVO": (
                    _safe_growth(
                        r.ATIVO_TOTAL,
                        ativo_ant,
                    )
                    if ano > 2023
                    else np.nan
                ),

                "CRESCIMENTO_PL": (
                    _safe_growth(
                        r.PL_CONSOLIDADO,
                        pl_ant,
                    )
                    if ano > 2023
                    else np.nan
                ),

                "CRESCIMENTO_LL": cresc_ll,
                "STATUS_CRESCIMENTO_LL": status_ll,
            }
        )

    return pd.DataFrame(linhas)


# ============================================================
# OUTLIERS / DIAGNÓSTICO
# ============================================================

METRICAS = [
    "CAPITALIZACAO_CONTABIL",
    "PASSIVOS_FINANCEIROS_ATIVO",
    "RBI_ATIVO_MEDIO",
    "RBI_RECEITA_INTERMEDIACAO",
    "RESULTADO_PRE_TRIB_ATIVO_MEDIO",
    "CRESCIMENTO_ATIVO",
    "CRESCIMENTO_PL",
    "CRESCIMENTO_LL",
]


def _percentil(
    valores: np.ndarray,
    p: float,
) -> float:
    return float(
        np.quantile(
            valores,
            p,
        )
    )


def resumo_metricas(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    resumos = []
    outliers = []

    for metrica in METRICAS:
        serie = pd.to_numeric(
            df[metrica],
            errors="coerce",
        )

        validos = serie.dropna()

        zeros = int(
            validos.eq(0).sum()
        )

        negativos = int(
            validos.lt(0).sum()
        )

        if validos.empty:
            resumos.append(
                {
                    "METRICA": metrica,
                    "N_TOTAL": len(df),
                    "N_VALIDOS": 0,
                    "N_ND": len(df),
                    "ZEROS": 0,
                    "NEGATIVOS": 0,
                    "MIN": np.nan,
                    "P25": np.nan,
                    "MEDIANA": np.nan,
                    "P75": np.nan,
                    "MAX": np.nan,
                    "OUTLIERS_IQR": 0,
                }
            )
            continue

        arr = validos.to_numpy(
            dtype=float
        )

        q1 = _percentil(
            arr,
            0.25,
        )

        q3 = _percentil(
            arr,
            0.75,
        )

        iqr = q3 - q1

        inferior = (
            q1
            - 1.5 * iqr
        )

        superior = (
            q3
            + 1.5 * iqr
        )

        mascara_outlier = (
            serie.lt(inferior)
            | serie.gt(superior)
        )

        casos = df[
            mascara_outlier.fillna(
                False
            )
        ][
            [
                "CD_CVM",
                "DENOM_CIA",
                "ANO",
                "ASSINATURA",
                metrica,
            ]
        ].copy()

        for caso in casos.itertuples(
            index=False
        ):
            outliers.append(
                {
                    "METRICA": metrica,
                    "CD_CVM": caso.CD_CVM,
                    "DENOM_CIA": caso.DENOM_CIA,
                    "ANO": caso.ANO,
                    "ASSINATURA": caso.ASSINATURA,
                    "VALOR": getattr(
                        caso,
                        metrica,
                    ),
                    "LIMITE_INFERIOR_IQR": inferior,
                    "LIMITE_SUPERIOR_IQR": superior,
                }
            )

        resumos.append(
            {
                "METRICA": metrica,
                "N_TOTAL": len(df),
                "N_VALIDOS": int(
                    validos.shape[0]
                ),
                "N_ND": int(
                    serie.isna().sum()
                ),
                "ZEROS": zeros,
                "NEGATIVOS": negativos,
                "MIN": float(
                    validos.min()
                ),
                "P25": q1,
                "MEDIANA": float(
                    validos.median()
                ),
                "P75": q3,
                "MAX": float(
                    validos.max()
                ),
                "OUTLIERS_IQR": len(
                    casos
                ),
            }
        )

    return (
        pd.DataFrame(resumos),
        pd.DataFrame(outliers),
    )


# ============================================================
# COBERTURA DO AUXILIAR
# ============================================================

def cobertura_auxiliar(
    pares: pd.DataFrame,
    at_2022: dict[str, float],
    pl_2022: dict[str, float],
) -> pd.DataFrame:
    empresas_2023 = (
        pares[
            pares["ANO"].eq(2023)
        ][
            [
                "CD_CVM",
                "DENOM_CIA",
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    empresas_2023[
        "ATIVO_2022_DISPONIVEL"
    ] = (
        empresas_2023[
            "CD_CVM"
        ]
        .isin(
            at_2022.keys()
        )
    )

    empresas_2023[
        "PL_2022_DISPONIVEL"
    ] = (
        empresas_2023[
            "CD_CVM"
        ]
        .isin(
            pl_2022.keys()
        )
    )

    return empresas_2023


# ============================================================
# VEREDITO METODOLÓGICO PROVISÓRIO
# ============================================================

def construir_veredito(
    resumo: pd.DataFrame,
    cobertura_aux: pd.DataFrame,
    metricas: pd.DataFrame,
) -> pd.DataFrame:
    stats = (
        resumo.set_index(
            "METRICA"
        )
        .to_dict(
            orient="index"
        )
    )

    aux_at_ok = int(
        cobertura_aux[
            "ATIVO_2022_DISPONIVEL"
        ].sum()
    )

    n_2023 = len(
        cobertura_aux
    )

    ll_status = (
        metricas.loc[
            metricas[
                "ANO"
            ]
            .gt(2023),
            "STATUS_CRESCIMENTO_LL",
        ]
        .value_counts()
        .to_dict()
    )

    linhas = [
        {
            "INDICADOR": "Capitalização Contábil (PL / Ativo)",
            "DECISAO_A3": "APROVAR",
            "REGRA": "PL Consolidado / Ativo Total",
            "COBERTURA_VALIDA": stats["CAPITALIZACAO_CONTABIL"]["N_VALIDOS"],
            "OBSERVACAO": (
                "Indicador contábil de capitalização; não confundir com Basileia/capital regulatório."
            ),
        },
        {
            "INDICADOR": "Passivos Financeiros / Ativo",
            "DECISAO_A3": "APROVAR COM NOTA DE HETEROGENEIDADE",
            "REGRA": "Soma dos componentes top-level de Passivos Financeiros / Ativo Total",
            "COBERTURA_VALIDA": stats["PASSIVOS_FINANCEIROS_ATIVO"]["N_VALIDOS"],
            "OBSERVACAO": (
                "Composição semanticamente fechada nos dois sublayouts. "
                "Valores baixos/zero podem ser economicamente reais em holdings/estruturas especiais."
            ),
        },
        {
            "INDICADOR": "Crescimento do Ativo",
            "DECISAO_A3": "APROVAR",
            "REGRA": "AT_t / AT_t-1 - 1; N/D se AT_t-1 = 0 ou ausente",
            "COBERTURA_VALIDA": stats["CRESCIMENTO_ATIVO"]["N_VALIDOS"],
            "OBSERVACAO": (
                "Não winsorizar automaticamente; outliers devem ser informativos."
            ),
        },
        {
            "INDICADOR": "Crescimento do PL",
            "DECISAO_A3": "APROVAR",
            "REGRA": "PL_t / PL_t-1 - 1; N/D se PL_t-1 = 0 ou ausente",
            "COBERTURA_VALIDA": stats["CRESCIMENTO_PL"]["N_VALIDOS"],
            "OBSERVACAO": (
                "Quedas e expansões extremas devem ser preservadas e sinalizadas, não truncadas."
            ),
        },
        {
            "INDICADOR": "Crescimento do Lucro Líquido",
            "DECISAO_A3": "APROVAR COM REGRA DE SINAL",
            "REGRA": (
                "Taxa percentual apenas para lucro anterior > 0 e lucro atual >= 0; "
                "casos de base zero/prejuízo/mudança de sinal recebem status qualitativo e N/A na taxa."
            ),
            "COBERTURA_VALIDA": stats["CRESCIMENTO_LL"]["N_VALIDOS"],
            "OBSERVACAO": str(ll_status),
        },
        {
            "INDICADOR": "RBI / Ativo Médio",
            "DECISAO_A3": (
                "APROVAR"
                if aux_at_ok == n_2023
                else "APROVAR COM N/D QUANDO FALTAR ATIVO ANTERIOR"
            ),
            "REGRA": "Resultado Bruto da Intermediação / Ativo Médio",
            "COBERTURA_VALIDA": stats["RBI_ATIVO_MEDIO"]["N_VALIDOS"],
            "OBSERVACAO": (
                f"Cobertura de Ativo 2022 para empresas FINANCEIRA de 2023: {aux_at_ok}/{n_2023}. "
                "Não denominar NIM."
            ),
        },
        {
            "INDICADOR": "RBI / Receita de Intermediação",
            "DECISAO_A3": "NÃO PRIORIZAR NO PAINEL PRINCIPAL",
            "REGRA": "RBI / Receita de Intermediação; N/D se receita = 0",
            "COBERTURA_VALIDA": stats["RBI_RECEITA_INTERMEDIACAO"]["N_VALIDOS"],
            "OBSERVACAO": (
                "Sensível à classificação contábil: algumas companhias apresentam despesa de intermediação zero, "
                "produzindo razão de 100%. Pode permanecer como métrica secundária/diagnóstica."
            ),
        },
        {
            "INDICADOR": "Resultado Pré-Tributos / Ativo Médio",
            "DECISAO_A3": (
                "APROVAR"
                if aux_at_ok == n_2023
                else "APROVAR COM N/D QUANDO FALTAR ATIVO ANTERIOR"
            ),
            "REGRA": "Resultado antes dos Tributos sobre o Lucro / Ativo Médio",
            "COBERTURA_VALIDA": stats["RESULTADO_PRE_TRIB_ATIVO_MEDIO"]["N_VALIDOS"],
            "OBSERVACAO": (
                "Métrica de rentabilidade pré-tributação; manter distinta do ROA líquido."
            ),
        },
    ]

    return pd.DataFrame(
        linhas
    )


# ============================================================
# EXPORTAÇÃO
# ============================================================

def ajustar_largura_planilha(
    writer: pd.ExcelWriter,
    sheet_name: str,
    df: pd.DataFrame,
) -> None:
    ws = writer.sheets[
        sheet_name
    ]

    for idx, coluna in enumerate(
        df.columns
    ):
        nome = str(
            coluna
        )

        valores = (
            df.iloc[
                :,
                idx,
            ]
            .head(500)
            .map(
                lambda x: (
                    ""
                    if pd.isna(x)
                    else str(x)
                )
            )
        )

        max_len = max(
            [len(nome)]
            + valores.map(
                len
            ).tolist()
        )

        ws.set_column(
            idx,
            idx,
            min(
                max(
                    max_len + 2,
                    10,
                ),
                55,
            ),
        )

    if len(
        df.columns
    ) > 0:
        ws.freeze_panes(
            1,
            0,
        )

        ws.autofilter(
            0,
            0,
            max(
                len(df),
                1,
            ),
            len(
                df.columns
            )
            - 1,
        )


def exportar(
    tabelas: dict[str, pd.DataFrame],
) -> Path:
    caminho = (
        SAIDA_DIR
        / "diagnostico_financeiras_etapa_a3.xlsx"
    )

    with pd.ExcelWriter(
        caminho,
        engine="xlsxwriter",
    ) as writer:
        for nome, df in tabelas.items():
            sheet = nome[:31]

            df.to_excel(
                writer,
                sheet_name=sheet,
                index=False,
            )

            ajustar_largura_planilha(
                writer,
                sheet,
                df,
            )

    for nome, df in tabelas.items():
        df.to_csv(
            SAIDA_DIR
            / f"{nome.lower()}.csv",
            index=False,
            encoding="utf-8-sig",
        )

    return caminho


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print(
        "="
        * 78
    )

    print(
        "SISTEMA CVM — ETAPA A.3 — DIAGNÓSTICO ECONÔMICO/ESTATÍSTICO FINANCEIRO"
    )

    print(
        "="
        * 78
    )

    print(
        "Modo: SOMENTE LEITURA | Nenhum indicador será implementado"
    )

    print()

    df = carregar_dfp()

    pares = identificar_pares_financeiros(
        df
    )

    base = extrair_financeiras(
        df,
        pares,
    )

    aux = carregar_auxiliar_2022()

    at_2022, pl_2022 = mapear_auxiliar(
        aux
    )

    cobertura_aux = cobertura_auxiliar(
        pares,
        at_2022,
        pl_2022,
    )

    metricas = construir_metricas(
        base,
        at_2022,
        pl_2022,
    )

    resumo, outliers = resumo_metricas(
        metricas
    )

    veredito = construir_veredito(
        resumo,
        cobertura_aux,
        metricas,
    )

    zeros_especiais = metricas[
        metricas[
            [
                "ATIVO_TOTAL",
                "PL_CONSOLIDADO",
                "LUCRO_LIQUIDO",
                "PASSIVOS_FINANCEIROS",
                "RECEITA_INTERMEDIACAO",
            ]
        ]
        .eq(0)
        .any(
            axis=1
        )
    ].copy()

    tabelas = {
        "00_VEREDITO": veredito,
        "01_COBERTURA_AUX": cobertura_aux,
        "02_METRICAS": metricas,
        "03_RESUMO": resumo,
        "04_OUTLIERS": outliers,
        "05_ZEROS_ESPECIAIS": zeros_especiais,
    }

    excel = exportar(
        tabelas
    )

    print(
        "COBERTURA DO ANO AUXILIAR 2022"
    )

    print(
        "-"
        * 78
    )

    print(
        "Ativo 2022 disponível: "
        f"{int(cobertura_aux['ATIVO_2022_DISPONIVEL'].sum())}"
        f"/{len(cobertura_aux)}"
    )

    print(
        "PL 2022 disponível: "
        f"{int(cobertura_aux['PL_2022_DISPONIVEL'].sum())}"
        f"/{len(cobertura_aux)}"
    )

    print()

    print(
        "RESUMO DOS INDICADORES CANDIDATOS"
    )

    print(
        "-"
        * 78
    )

    print(
        resumo.to_string(
            index=False
        )
    )

    print()

    print(
        "VEREDITO METODOLÓGICO PROVISÓRIO"
    )

    print(
        "-"
        * 78
    )

    print(
        veredito[
            [
                "INDICADOR",
                "DECISAO_A3",
                "COBERTURA_VALIDA",
            ]
        ].to_string(
            index=False
        )
    )

    print()

    print(
        "SAÍDA"
    )

    print(
        "-"
        * 78
    )

    print(
        excel
    )

    print()

    print(
        "ETAPA A.3 concluída. "
        "Nenhuma fórmula foi incorporada ao sistema."
    )


if __name__ == "__main__":
    main()

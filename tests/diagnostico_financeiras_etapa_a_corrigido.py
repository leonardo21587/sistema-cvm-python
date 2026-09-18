from __future__ import annotations

"""
ETAPA A — Auditoria estrutural das companhias FINANCEIRA
Sistema-CVM-Python

Objetivo:
- NÃO altera app.py, src/indicadores.py, ETL ou banco.
- Abre DuckDB somente em modo read_only.
- Identifica companhias FINANCEIRA usando src/layouts_cvm.py.
- Audita contas fixas BPA/BPP/DRE em 2023-2025.
- Mede frequência/cobertura estrutural.
- Sinaliza ambiguidades semânticas de CD_CONTA/DS_CONTA.
- Produz matriz de cobertura de indicadores candidatos SEM calcular fórmulas novas.
"""

from dataclasses import dataclass
from pathlib import Path
import sys
import re

import numpy as np
import pandas as pd


# ============================================================
# RAIZ DO PROJETO / IMPORTS
# ============================================================

ARQUIVO = Path(__file__).resolve()

if ARQUIVO.parent.name.lower() == "tests":
    ROOT_DIR = ARQUIVO.parents[1]
else:
    ROOT_DIR = ARQUIVO.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar  # noqa: E402
from src.layouts_cvm import (  # noqa: E402
    LAYOUT_FINANCEIRA,
    detectar_layout,
    normalizar_descricao,
    resolver_codigo_ll,
    resolver_codigo_pl,
)


ANOS = [2023, 2024, 2025]
DEMONSTRACOES = ["BPA", "BPP", "DRE"]

SAIDA_DIR = ROOT_DIR / "data" / "auditoria" / "financeiras_etapa_a"
SAIDA_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# UTILITÁRIOS
# ============================================================

def _texto(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip()


def _is_conta_fixa(serie: pd.Series) -> pd.Series:
    """
    CVM normalmente usa S/N em ST_CONTA_FIXA.
    Mantemos tolerância apenas para representações textuais equivalentes.
    """
    s = (
        serie.astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )
    return s.isin({"S", "SIM", "1", "TRUE", "T"})


def _join_unicos(valores, limite: int | None = None) -> str:
    itens = sorted(
        {
            _texto(v)
            for v in valores
            if _texto(v)
        }
    )
    if limite is not None and len(itens) > limite:
        extras = len(itens) - limite
        itens = itens[:limite] + [f"... (+{extras})"]
    return " | ".join(itens)


def _normalizar_cd_cvm(serie: pd.Series) -> pd.Series:
    return (
        serie.astype("string")
        .fillna("")
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .str.zfill(6)
    )




def _markdown_table(df: pd.DataFrame) -> str:
    """Tabela Markdown simples, sem dependência de tabulate."""
    if df is None or df.empty:
        if df is not None and len(df.columns):
            cab = "| " + " | ".join(map(str, df.columns)) + " |"
            sep = "| " + " | ".join(["---"] * len(df.columns)) + " |"
            return cab + "\n" + sep
        return "_Sem registros._"

    d = df.copy()

    def esc(v: object) -> str:
        if v is None or pd.isna(v):
            return ""
        return str(v).replace("|", r"\|").replace("\n", " ")

    cab = "| " + " | ".join(esc(c) for c in d.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(d.columns)) + " |"
    linhas = [
        "| " + " | ".join(esc(v) for v in row) + " |"
        for row in d.itertuples(index=False, name=None)
    ]
    return "\n".join([cab, sep, *linhas])

def _categoria_frequencia(cobertura_par_pct: float) -> str:
    if cobertura_par_pct >= 100 - 1e-12:
        return "UNIVERSAL"
    if cobertura_par_pct >= 80:
        return "QUASE_UNIVERSAL"
    if cobertura_par_pct >= 50:
        return "COMUM"
    return "RARA"


# ============================================================
# CARGA — SOMENTE LEITURA
# ============================================================

def carregar_base() -> tuple[pd.DataFrame, pd.DataFrame]:
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

        empresas = con.execute(
            """
            SELECT
                CD_CVM,
                CNPJ_CIA,
                DENOM_CIA
            FROM empresas
            """
        ).fetchdf()

    finally:
        con.close()

    df["CD_CVM"] = _normalizar_cd_cvm(df["CD_CVM"])
    empresas["CD_CVM"] = _normalizar_cd_cvm(empresas["CD_CVM"])

    df["ANO"] = pd.to_numeric(df["ANO"], errors="coerce").astype("Int64")
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
    df["DS_NORM"] = df["DS_CONTA"].map(normalizar_descricao)
    df["CONTA_FIXA"] = _is_conta_fixa(df["ST_CONTA_FIXA"])

    return df, empresas


# ============================================================
# DETECÇÃO DO LAYOUT POR COMPANHIA / ANO
# ============================================================

def detectar_layouts_anuais(df: pd.DataFrame) -> pd.DataFrame:
    linhas: list[dict] = []

    for (cd_cvm, ano), g in df.groupby(["CD_CVM", "ANO"], sort=True):
        bpp = g[g["DEMONSTRACAO"].eq("BPP")][
            ["CD_CONTA", "DS_CONTA"]
        ].copy()
        dre = g[g["DEMONSTRACAO"].eq("DRE")][
            ["CD_CONTA", "DS_CONTA"]
        ].copy()

        layout = detectar_layout(bpp, dre)

        denom = (
            g["DENOM_CIA"]
            .dropna()
            .astype(str)
            .iloc[0]
            if g["DENOM_CIA"].notna().any()
            else ""
        )

        linhas.append(
            {
                "CD_CVM": cd_cvm,
                "DENOM_CIA": denom,
                "ANO": int(ano),
                "LAYOUT": layout.codigo,
                "CODIGO_PL": resolver_codigo_pl(bpp),
                "CODIGO_LL": resolver_codigo_ll(dre),
            }
        )

    return pd.DataFrame(linhas)


def identificar_financeiras(
    layouts_anuais: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    finance_any = set(
        layouts_anuais.loc[
            layouts_anuais["LAYOUT"].eq(LAYOUT_FINANCEIRA),
            "CD_CVM",
        ]
    )

    resumo = (
        layouts_anuais[
            layouts_anuais["CD_CVM"].isin(finance_any)
        ]
        .groupby(["CD_CVM", "DENOM_CIA"], as_index=False)
        .agg(
            ANOS_DISPONIVEIS=("ANO", "nunique"),
            ANOS_FINANCEIRA=(
                "LAYOUT",
                lambda s: int((s == LAYOUT_FINANCEIRA).sum()),
            ),
            LAYOUTS=("LAYOUT", _join_unicos),
            CODIGOS_PL=("CODIGO_PL", _join_unicos),
            CODIGOS_LL=("CODIGO_LL", _join_unicos),
        )
    )

    resumo["FINANCEIRA_ESTAVEL_3A"] = (
        resumo["ANOS_DISPONIVEIS"].eq(3)
        & resumo["ANOS_FINANCEIRA"].eq(3)
        & resumo["LAYOUTS"].eq(LAYOUT_FINANCEIRA)
    )

    return (
        layouts_anuais[
            layouts_anuais["CD_CVM"].isin(finance_any)
        ].copy(),
        resumo.sort_values(["DENOM_CIA", "CD_CVM"]).reset_index(drop=True),
    )


# ============================================================
# ASSINATURAS ESTRUTURAIS — NÃO SÃO CLASSIFICAÇÃO REGULATÓRIA
# ============================================================

def _tem_desc(
    g: pd.DataFrame,
    demonstracao: str | None = None,
    exata: str | None = None,
    contem: str | None = None,
) -> bool:
    d = g
    if demonstracao:
        d = d[d["DEMONSTRACAO"].eq(demonstracao)]

    s = d["DS_NORM"]

    if exata is not None:
        alvo = normalizar_descricao(exata)
        return bool(s.eq(alvo).any())

    if contem is not None:
        alvo = normalizar_descricao(contem)
        return bool(s.str.contains(re.escape(alvo), regex=True, na=False).any())

    return False


def construir_assinaturas(
    df_fin: pd.DataFrame,
    layouts_fin: pd.DataFrame,
    companhias: pd.DataFrame,
) -> pd.DataFrame:
    linhas: list[dict] = []

    for cd_cvm in sorted(companhias["CD_CVM"].unique()):
        g = df_fin[
            df_fin["CD_CVM"].eq(cd_cvm)
            & df_fin["CONTA_FIXA"]
        ].copy()

        lay = layouts_fin[layouts_fin["CD_CVM"].eq(cd_cvm)]

        nome = (
            companhias.loc[
                companhias["CD_CVM"].eq(cd_cvm),
                "DENOM_CIA",
            ].iloc[0]
        )

        has_receita_inter = _tem_desc(
            g, "DRE", exata="Receitas da Intermediação Financeira"
        )
        has_despesa_inter = _tem_desc(
            g, "DRE", exata="Despesas da Intermediação Financeira"
        )
        has_rbit = _tem_desc(
            g, "DRE", exata="Resultado Bruto da Intermediação Financeira"
        )
        has_depositos = _tem_desc(
            g, "BPP", contem="Depósitos"
        )
        has_credito = _tem_desc(
            g, "BPA", contem="Operações de Crédito"
        )
        has_pass_fin = _tem_desc(
            g, "BPP", contem="Passivos Financeiros"
        )

        estavel = bool(
            lay["LAYOUT"].eq(LAYOUT_FINANCEIRA).all()
            and lay["ANO"].nunique() == 3
        )

        if not estavel:
            categoria = "CASO_INCOMPLETO_OU_ESPECIAL"
        elif (
            has_receita_inter
            and has_despesa_inter
            and has_rbit
            and has_depositos
            and has_credito
        ):
            categoria = "INTERMEDIACAO_BANCARIA_COMPLETA"
        elif has_receita_inter and has_despesa_inter:
            categoria = "INTERMEDIACAO_FINANCEIRA"
        else:
            categoria = "HOLDING_OU_ESTRUTURA_ATIPICA_A_REVISAR"

        linhas.append(
            {
                "CD_CVM": cd_cvm,
                "DENOM_CIA": nome,
                "PADRAO_PL": _join_unicos(lay["CODIGO_PL"]),
                "PADRAO_LL": _join_unicos(lay["CODIGO_LL"]),
                "FINANCEIRA_ESTAVEL_3A": estavel,
                "TEM_RECEITA_INTERMEDIACAO": has_receita_inter,
                "TEM_DESPESA_INTERMEDIACAO": has_despesa_inter,
                "TEM_RESULTADO_BRUTO_INTERMEDIACAO": has_rbit,
                "TEM_DEPOSITOS": has_depositos,
                "TEM_OPERACOES_CREDITO": has_credito,
                "TEM_PASSIVOS_FINANCEIROS": has_pass_fin,
                "CATEGORIA_ESTRUTURAL_DIAGNOSTICA": categoria,
                "OBSERVACAO": (
                    "Categoria baseada apenas na assinatura de contas fixas da DFP; "
                    "não equivale a classificação regulatória/legal."
                ),
            }
        )

    return pd.DataFrame(linhas).sort_values(
        ["CATEGORIA_ESTRUTURAL_DIAGNOSTICA", "DENOM_CIA", "CD_CVM"]
    ).reset_index(drop=True)


# ============================================================
# FREQUÊNCIA DE CONTAS FIXAS
# ============================================================

def frequencia_contas(
    df_fin: pd.DataFrame,
    companhias: pd.DataFrame,
) -> pd.DataFrame:
    d = df_fin[df_fin["CONTA_FIXA"]].copy()
    d["EMPRESA_ANO"] = (
        d["CD_CVM"].astype(str)
        + "-"
        + d["ANO"].astype(str)
    )

    total_empresas = companhias["CD_CVM"].nunique()
    total_pares_esperados = total_empresas * len(ANOS)

    freq = (
        d.groupby(
            ["DEMONSTRACAO", "CD_CONTA", "DS_NORM"],
            as_index=False,
            dropna=False,
        )
        .agg(
            DS_CONTA_EXEMPLO=("DS_CONTA", "first"),
            DESCRICOES_ORIGINAIS=("DS_CONTA", _join_unicos),
            N_EMPRESAS=("CD_CVM", "nunique"),
            N_EMPRESA_ANO=("EMPRESA_ANO", "nunique"),
            N_ANOS=("ANO", "nunique"),
            EMPRESAS=("DENOM_CIA", lambda s: _join_unicos(s, limite=30)),
        )
    )

    # Empresas com presença em todos os 3 anos para a conta semântica exata.
    pres = (
        d.groupby(
            ["DEMONSTRACAO", "CD_CONTA", "DS_NORM", "CD_CVM"],
            as_index=False,
        )["ANO"]
        .nunique()
        .rename(columns={"ANO": "N_ANOS_EMPRESA"})
    )

    full = (
        pres[pres["N_ANOS_EMPRESA"].eq(len(ANOS))]
        .groupby(
            ["DEMONSTRACAO", "CD_CONTA", "DS_NORM"],
            as_index=False,
        )["CD_CVM"]
        .nunique()
        .rename(columns={"CD_CVM": "N_EMPRESAS_3_ANOS"})
    )

    freq = freq.merge(
        full,
        on=["DEMONSTRACAO", "CD_CONTA", "DS_NORM"],
        how="left",
    )
    freq["N_EMPRESAS_3_ANOS"] = (
        freq["N_EMPRESAS_3_ANOS"]
        .fillna(0)
        .astype(int)
    )

    freq["COBERTURA_EMPRESAS_PCT"] = (
        100 * freq["N_EMPRESAS"] / total_empresas
    )
    freq["COBERTURA_EMPRESA_ANO_PCT"] = (
        100 * freq["N_EMPRESA_ANO"] / total_pares_esperados
    )
    freq["COBERTURA_3_ANOS_PCT"] = (
        100 * freq["N_EMPRESAS_3_ANOS"] / total_empresas
    )
    freq["CLASSE_FREQUENCIA"] = (
        freq["COBERTURA_EMPRESA_ANO_PCT"]
        .map(_categoria_frequencia)
    )

    return freq.sort_values(
        [
            "DEMONSTRACAO",
            "COBERTURA_EMPRESA_ANO_PCT",
            "CD_CONTA",
            "DS_NORM",
        ],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)


# ============================================================
# AMBIGUIDADES SEMÂNTICAS
# ============================================================

def conflitos_por_codigo(df_fin: pd.DataFrame) -> pd.DataFrame:
    d = df_fin[df_fin["CONTA_FIXA"]].copy()

    out = (
        d.groupby(
            ["DEMONSTRACAO", "CD_CONTA"],
            as_index=False,
        )
        .agg(
            N_DESCRICOES=("DS_NORM", "nunique"),
            DESCRICOES=("DS_CONTA", _join_unicos),
            N_EMPRESAS=("CD_CVM", "nunique"),
            EMPRESAS=("DENOM_CIA", lambda s: _join_unicos(s, limite=30)),
        )
    )

    return (
        out[out["N_DESCRICOES"] > 1]
        .sort_values(
            ["N_DESCRICOES", "N_EMPRESAS", "DEMONSTRACAO", "CD_CONTA"],
            ascending=[False, False, True, True],
        )
        .reset_index(drop=True)
    )


def descricoes_em_multiplos_codigos(df_fin: pd.DataFrame) -> pd.DataFrame:
    d = df_fin[df_fin["CONTA_FIXA"]].copy()

    out = (
        d.groupby(
            ["DEMONSTRACAO", "DS_NORM"],
            as_index=False,
        )
        .agg(
            DS_CONTA_EXEMPLO=("DS_CONTA", "first"),
            N_CODIGOS=("CD_CONTA", "nunique"),
            CODIGOS=("CD_CONTA", _join_unicos),
            N_EMPRESAS=("CD_CVM", "nunique"),
            EMPRESAS=("DENOM_CIA", lambda s: _join_unicos(s, limite=30)),
        )
    )

    return (
        out[out["N_CODIGOS"] > 1]
        .sort_values(
            ["N_EMPRESAS", "N_CODIGOS", "DEMONSTRACAO", "DS_NORM"],
            ascending=[False, False, True, True],
        )
        .reset_index(drop=True)
    )


# ============================================================
# CONCEITOS SEMÂNTICOS PARA MATRIZ DE COBERTURA
# ============================================================

@dataclass(frozen=True)
class Conceito:
    codigo: str
    demonstracao: str
    tipo: str
    alvo: str
    observacao: str = ""


CONCEITOS = [
    Conceito(
        "ATIVO_TOTAL",
        "BPA",
        "codigo_exato",
        "1",
        "Conta estrutural do Ativo Total.",
    ),
    Conceito(
        "PL_CONSOLIDADO",
        "BPP",
        "descricao_exata",
        "Patrimônio Líquido Consolidado",
        "Descrição exata; o código pode ser 2.07 ou 2.08.",
    ),
    Conceito(
        "LUCRO_LIQUIDO_CONSOLIDADO",
        "DRE",
        "descricao_exata_multipla",
        "Lucro/Prejuízo Consolidado do Período || "
        "Lucro ou Prejuízo Líquido Consolidado do Período",
        "Descrição exata compatível com resolver_codigo_ll().",
    ),
    Conceito(
        "PASSIVOS_FINANCEIROS",
        "BPP",
        "descricao_contem",
        "Passivos Financeiros",
        "Diagnóstico estrito: se houver mais de uma conta candidata no mesmo empresa-ano, marca ambiguidade.",
    ),
    Conceito(
        "RECEITAS_INTERMEDIACAO",
        "DRE",
        "descricao_exata",
        "Receitas da Intermediação Financeira",
        "Não assume equivalência com outras receitas bancárias.",
    ),
    Conceito(
        "DESPESAS_INTERMEDIACAO",
        "DRE",
        "descricao_exata",
        "Despesas da Intermediação Financeira",
        "Não assume equivalência com outras despesas bancárias.",
    ),
    Conceito(
        "RESULTADO_BRUTO_INTERMEDIACAO",
        "DRE",
        "descricao_exata",
        "Resultado Bruto da Intermediação Financeira",
        "Conceito candidato ainda não aprovado.",
    ),
    Conceito(
        "RESULTADO_ANTES_TRIBUTOS",
        "DRE",
        "descricao_exata",
        "Resultado Antes dos Tributos sobre o Lucro",
        "Near-misses são listados separadamente; não são agregados automaticamente.",
    ),
]


def _mascara_conceito(df: pd.DataFrame, conceito: Conceito) -> pd.Series:
    base = df["DEMONSTRACAO"].eq(conceito.demonstracao)

    if conceito.tipo == "codigo_exato":
        return base & df["CD_CONTA"].eq(conceito.alvo)

    if conceito.tipo == "descricao_exata":
        alvo = normalizar_descricao(conceito.alvo)
        return base & df["DS_NORM"].eq(alvo)

    if conceito.tipo == "descricao_exata_multipla":
        alvos = {
            normalizar_descricao(x.strip())
            for x in conceito.alvo.split("||")
        }
        return base & df["DS_NORM"].isin(alvos)

    if conceito.tipo == "descricao_contem":
        alvo = normalizar_descricao(conceito.alvo)
        return base & df["DS_NORM"].str.contains(
            re.escape(alvo),
            regex=True,
            na=False,
        )

    raise ValueError(f"Tipo de conceito não tratado: {conceito.tipo}")


def mapear_conceitos(
    df_fin: pd.DataFrame,
    companhias: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = df_fin[df_fin["CONTA_FIXA"]].copy()
    pares = pd.MultiIndex.from_product(
        [sorted(companhias["CD_CVM"].unique()), ANOS],
        names=["CD_CVM", "ANO"],
    ).to_frame(index=False)

    nomes = (
        companhias[["CD_CVM", "DENOM_CIA"]]
        .drop_duplicates("CD_CVM")
    )
    pares = pares.merge(nomes, on="CD_CVM", how="left")

    detalhes: list[pd.DataFrame] = []
    resumos: list[dict] = []

    for conceito in CONCEITOS:
        cand = d[_mascara_conceito(d, conceito)].copy()

        agg = (
            cand.groupby(["CD_CVM", "ANO"], as_index=False)
            .agg(
                N_MATCHES=("CD_CONTA", "size"),
                N_CODIGOS=("CD_CONTA", "nunique"),
                CONTAS_CVM=(
                    "CD_CONTA",
                    lambda s: _join_unicos(s),
                ),
                DESCRICOES=(
                    "DS_CONTA",
                    lambda s: _join_unicos(s),
                ),
            )
        )

        mapa = pares.merge(
            agg,
            on=["CD_CVM", "ANO"],
            how="left",
        )
        mapa["CONCEITO"] = conceito.codigo
        mapa["N_MATCHES"] = mapa["N_MATCHES"].fillna(0).astype(int)
        mapa["N_CODIGOS"] = mapa["N_CODIGOS"].fillna(0).astype(int)
        mapa["PRESENTE_UNIVOCO"] = mapa["N_MATCHES"].eq(1)
        mapa["AUSENTE"] = mapa["N_MATCHES"].eq(0)
        mapa["AMBIGUO"] = mapa["N_MATCHES"].gt(1)

        detalhes.append(mapa)

        por_empresa = (
            mapa.groupby(["CD_CVM", "DENOM_CIA"], as_index=False)
            .agg(
                ANOS_PRESENTE_UNIVOCO=("PRESENTE_UNIVOCO", "sum"),
                ANOS_AMBIGUO=("AMBIGUO", "sum"),
            )
        )
        cobertas = por_empresa[
            por_empresa["ANOS_PRESENTE_UNIVOCO"].eq(3)
            & por_empresa["ANOS_AMBIGUO"].eq(0)
        ]

        contas = _join_unicos(
            cand.apply(
                lambda r: (
                    f"{r['DEMONSTRACAO']} {r['CD_CONTA']} — {r['DS_CONTA']}"
                ),
                axis=1,
            ),
            limite=20,
        )

        total_empresas = companhias["CD_CVM"].nunique()
        total_pares = total_empresas * len(ANOS)

        resumos.append(
            {
                "CONCEITO": conceito.codigo,
                "DEMONSTRACAO": conceito.demonstracao,
                "REGRA_DIAGNOSTICA": f"{conceito.tipo}: {conceito.alvo}",
                "CONTAS_CVM_OBSERVADAS": contas,
                "EMPRESAS_COBERTAS_3A": len(cobertas),
                "COBERTURA_EMPRESAS_3A_PCT": (
                    100 * len(cobertas) / total_empresas
                    if total_empresas
                    else np.nan
                ),
                "PARES_PRESENTES_UNIVOCOS": int(mapa["PRESENTE_UNIVOCO"].sum()),
                "COBERTURA_EMPRESA_ANO_PCT": (
                    100 * mapa["PRESENTE_UNIVOCO"].sum() / total_pares
                    if total_pares
                    else np.nan
                ),
                "PARES_AMBIGUOS": int(mapa["AMBIGUO"].sum()),
                "EMPRESAS_COBERTAS": _join_unicos(cobertas["DENOM_CIA"]),
                "OBSERVACAO": conceito.observacao,
            }
        )

    return (
        pd.concat(detalhes, ignore_index=True),
        pd.DataFrame(resumos),
    )


# ============================================================
# NEAR-MISSES — SOMENTE DIAGNÓSTICO
# ============================================================

def localizar_near_misses(df_fin: pd.DataFrame) -> pd.DataFrame:
    d = df_fin[df_fin["CONTA_FIXA"]].copy()

    termos = {
        "PASSIVOS_FINANCEIROS": ["PASSIV", "FINANCEIR"],
        "RECEITAS_INTERMEDIACAO": ["RECEIT", "INTERMED"],
        "DESPESAS_INTERMEDIACAO": ["DESPES", "INTERMED"],
        "RESULTADO_BRUTO_INTERMEDIACAO": ["RESULTADO", "INTERMED"],
        "RESULTADO_ANTES_TRIBUTOS": ["RESULTADO", "TRIBUT"],
    }

    linhas = []

    for conceito, palavras in termos.items():
        mask = pd.Series(True, index=d.index)
        for palavra in palavras:
            mask &= d["DS_NORM"].str.contains(palavra, na=False)

        c = d[mask].copy()

        if c.empty:
            continue

        tmp = (
            c.groupby(
                ["DEMONSTRACAO", "CD_CONTA", "DS_NORM"],
                as_index=False,
            )
            .agg(
                DS_CONTA_EXEMPLO=("DS_CONTA", "first"),
                N_EMPRESAS=("CD_CVM", "nunique"),
                N_EMPRESA_ANO=(
                    "ANO",
                    "size",
                ),
                EMPRESAS=("DENOM_CIA", lambda s: _join_unicos(s, limite=30)),
            )
        )
        tmp.insert(0, "CONCEITO_REFERENCIA", conceito)
        linhas.append(tmp)

    if not linhas:
        return pd.DataFrame(
            columns=[
                "CONCEITO_REFERENCIA",
                "DEMONSTRACAO",
                "CD_CONTA",
                "DS_NORM",
                "DS_CONTA_EXEMPLO",
                "N_EMPRESAS",
                "N_EMPRESA_ANO",
                "EMPRESAS",
            ]
        )

    return pd.concat(linhas, ignore_index=True).sort_values(
        ["CONCEITO_REFERENCIA", "N_EMPRESAS", "DEMONSTRACAO", "CD_CONTA"],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)


# ============================================================
# MATRIZ DE COBERTURA DOS INDICADORES CANDIDATOS
# ============================================================

CANDIDATOS = [
    {
        "INDICADOR_CANDIDATO": "ROA",
        "FORMULA_DIAGNOSTICA": "Lucro Líquido / Ativo Médio",
        "CONCEITOS": ["LUCRO_LIQUIDO_CONSOLIDADO", "ATIVO_TOTAL"],
        "STATUS": "JÁ APROVADO",
        "LIMITACAO": (
            "A cobertura estrutural 2023-2025 não substitui a validação do saldo auxiliar 2022 "
            "necessário ao Ativo Médio de 2023."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "ROE",
        "FORMULA_DIAGNOSTICA": "Lucro Líquido / Patrimônio Líquido Médio",
        "CONCEITOS": ["LUCRO_LIQUIDO_CONSOLIDADO", "PL_CONSOLIDADO"],
        "STATUS": "JÁ APROVADO",
        "LIMITACAO": (
            "A cobertura estrutural 2023-2025 não substitui a validação do saldo auxiliar 2022 "
            "necessário ao PL Médio de 2023."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Patrimônio Líquido / Ativo Total",
        "FORMULA_DIAGNOSTICA": "PL Consolidado / Ativo Total",
        "CONCEITOS": ["PL_CONSOLIDADO", "ATIVO_TOTAL"],
        "STATUS": "CANDIDATO",
        "LIMITACAO": (
            "Boa comparabilidade contábil não implica interpretação prudencial; não substitui capital regulatório."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Passivos Financeiros / Ativo Total",
        "FORMULA_DIAGNOSTICA": "Passivos Financeiros / Ativo Total",
        "CONCEITOS": ["PASSIVOS_FINANCEIROS", "ATIVO_TOTAL"],
        "STATUS": "CANDIDATO — CONTA A VALIDAR",
        "LIMITACAO": (
            "A expressão 'Passivos Financeiros' pode representar agregados diferentes entre layouts. "
            "Somente empresa-ano com uma única conta candidata é contado como cobertura estrita."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Crescimento do Ativo Total",
        "FORMULA_DIAGNOSTICA": "AT_t / AT_t-1 - 1",
        "CONCEITOS": ["ATIVO_TOTAL"],
        "STATUS": "CANDIDATO",
        "LIMITACAO": (
            "Com 2023-2025, a cobertura interna permite taxas 2024/2023 e 2025/2024. "
            "2023 exigiria dado auxiliar 2022."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Crescimento do Patrimônio Líquido",
        "FORMULA_DIAGNOSTICA": "PL_t / PL_t-1 - 1",
        "CONCEITOS": ["PL_CONSOLIDADO"],
        "STATUS": "CANDIDATO",
        "LIMITACAO": (
            "Com 2023-2025, a cobertura interna permite taxas 2024/2023 e 2025/2024."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Crescimento do Lucro Líquido",
        "FORMULA_DIAGNOSTICA": "LL_t / LL_t-1 - 1",
        "CONCEITOS": ["LUCRO_LIQUIDO_CONSOLIDADO"],
        "STATUS": "CANDIDATO",
        "LIMITACAO": (
            "Taxas podem perder interpretação econômica quando o lucro muda de sinal; "
            "a matriz mede apenas disponibilidade estrutural."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Resultado Bruto da Intermediação / Ativo Médio",
        "FORMULA_DIAGNOSTICA": "RBI / Ativo Médio",
        "CONCEITOS": ["RESULTADO_BRUTO_INTERMEDIACAO", "ATIVO_TOTAL"],
        "STATUS": "CANDIDATO",
        "LIMITACAO": (
            "Só é comparável onde a rubrica de intermediação é semanticamente equivalente. "
            "Para 2023, Ativo Médio exige saldo auxiliar 2022."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Resultado Bruto da Intermediação / Receita de Intermediação",
        "FORMULA_DIAGNOSTICA": "RBI / Receitas da Intermediação Financeira",
        "CONCEITOS": [
            "RESULTADO_BRUTO_INTERMEDIACAO",
            "RECEITAS_INTERMEDIACAO",
        ],
        "STATUS": "CANDIDATO",
        "LIMITACAO": (
            "Não assumir que todas as companhias financeiras reconhecem receita de intermediação "
            "com a mesma estrutura de DRE."
        ),
    },
    {
        "INDICADOR_CANDIDATO": "Resultado antes dos tributos / Ativo",
        "FORMULA_DIAGNOSTICA": "Resultado antes dos tributos / Ativo",
        "CONCEITOS": ["RESULTADO_ANTES_TRIBUTOS", "ATIVO_TOTAL"],
        "STATUS": "CANDIDATO",
        "LIMITACAO": (
            "Descrições próximas, porém não idênticas, não são combinadas automaticamente nesta etapa."
        ),
    },
]


def matriz_cobertura_candidatos(
    detalhe_conceitos: pd.DataFrame,
    companhias: pd.DataFrame,
) -> pd.DataFrame:
    total_empresas = companhias["CD_CVM"].nunique()

    # Presença unívoca conceito x empresa x ano
    p = detalhe_conceitos[
        ["CONCEITO", "CD_CVM", "ANO", "PRESENTE_UNIVOCO"]
    ].copy()

    linhas = []

    for cand in CANDIDATOS:
        conceitos = cand["CONCEITOS"]

        sub = p[p["CONCEITO"].isin(conceitos)].copy()

        wide = (
            sub.pivot_table(
                index=["CD_CVM", "ANO"],
                columns="CONCEITO",
                values="PRESENTE_UNIVOCO",
                aggfunc="max",
                fill_value=False,
            )
            .reset_index()
        )

        for conceito in conceitos:
            if conceito not in wide.columns:
                wide[conceito] = False

        wide["COBERTO_NO_ANO"] = wide[conceitos].all(axis=1)

        por_empresa = (
            wide.groupby("CD_CVM", as_index=False)
            .agg(
                ANOS_COBERTOS=("COBERTO_NO_ANO", "sum"),
            )
        )
        cobertas = por_empresa[
            por_empresa["ANOS_COBERTOS"].eq(len(ANOS))
        ]["CD_CVM"]

        nomes = (
            companhias[
                companhias["CD_CVM"].isin(cobertas)
            ]["DENOM_CIA"]
        )

        n_pares_cobertos = int(wide["COBERTO_NO_ANO"].sum())
        total_pares = total_empresas * len(ANOS)

        linhas.append(
            {
                "INDICADOR_CANDIDATO": cand["INDICADOR_CANDIDATO"],
                "FORMULA": cand["FORMULA_DIAGNOSTICA"],
                "CONCEITOS_CVM_NECESSARIOS": " + ".join(conceitos),
                "COBERTURA_EMPRESAS_3A_PCT": (
                    100 * len(cobertas) / total_empresas
                    if total_empresas
                    else np.nan
                ),
                "N_EMPRESAS_COBERTAS_3A": int(len(cobertas)),
                "N_EMPRESAS_TOTAL": int(total_empresas),
                "COBERTURA_EMPRESA_ANO_PCT": (
                    100 * n_pares_cobertos / total_pares
                    if total_pares
                    else np.nan
                ),
                "EMPRESAS_COBERTAS_3A": _join_unicos(nomes),
                "STATUS_METODOLOGICO": cand["STATUS"],
                "LIMITACAO_METODOLOGICA": cand["LIMITACAO"],
            }
        )

    return pd.DataFrame(linhas)


# ============================================================
# EXPORTAÇÃO
# ============================================================

def salvar_csv(df: pd.DataFrame, nome: str) -> Path:
    caminho = SAIDA_DIR / nome
    df.to_csv(caminho, index=False, encoding="utf-8-sig")
    return caminho


def ajustar_largura_planilha(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    ws = writer.sheets[sheet_name]
    max_cols = min(len(df.columns), 30)

    for idx in range(max_cols):
        nome = str(df.columns[idx])
        valores = (
            df.iloc[:, idx]
            .head(500)
            .map(lambda x: "" if pd.isna(x) else str(x))
        )
        max_len = max(
            [len(nome)]
            + valores.map(len).tolist()
        )
        ws.set_column(idx, idx, min(max(max_len + 2, 10), 45))

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))


def exportar_excel(
    tabelas: dict[str, pd.DataFrame],
) -> Path:
    caminho = SAIDA_DIR / "diagnostico_financeiras_etapa_a.xlsx"

    with pd.ExcelWriter(
        caminho,
        engine="xlsxwriter",
    ) as writer:
        for sheet, df in tabelas.items():
            nome = sheet[:31]
            df.to_excel(writer, sheet_name=nome, index=False)
            ajustar_largura_planilha(writer, nome, df)

    return caminho


def gerar_resumo_markdown(
    companhias: pd.DataFrame,
    layouts_fin: pd.DataFrame,
    assinaturas: pd.DataFrame,
    freq: pd.DataFrame,
    matriz: pd.DataFrame,
    conflitos_cd: pd.DataFrame,
    desc_multi_cd: pd.DataFrame,
) -> Path:
    total = companhias["CD_CVM"].nunique()
    estaveis = int(companhias["FINANCEIRA_ESTAVEL_3A"].sum())

    padroes = (
        layouts_fin.groupby(["CODIGO_PL", "CODIGO_LL"], dropna=False)
        .agg(
            EMPRESAS=("CD_CVM", "nunique"),
            EMPRESA_ANO=("CD_CVM", "size"),
        )
        .reset_index()
        .sort_values(["EMPRESAS", "EMPRESA_ANO"], ascending=False)
    )

    universais = freq[freq["CLASSE_FREQUENCIA"].eq("UNIVERSAL")]
    quase = freq[freq["CLASSE_FREQUENCIA"].eq("QUASE_UNIVERSAL")]

    cats = (
        assinaturas["CATEGORIA_ESTRUTURAL_DIAGNOSTICA"]
        .value_counts()
        .rename_axis("CATEGORIA")
        .reset_index(name="EMPRESAS")
    )

    linhas = [
        "# ETAPA A — Auditoria estrutural FINANCEIRA",
        "",
        "## Escopo",
        f"- Companhias identificadas como FINANCEIRA em pelo menos um ano: **{total}**",
        f"- Companhias FINANCEIRA estáveis em 2023–2025: **{estaveis}**",
        "- Período: **2023–2025**",
        "- Demonstrações: **BPA, BPP e DRE consolidadas**",
        "- Base: somente leitura do DuckDB aprovado.",
        "- Nenhuma fórmula nova foi implementada.",
        "",
        "## Padrões PL / Lucro Líquido",
        "",
        _markdown_table(padroes),
        "",
        "## Famílias estruturais diagnósticas",
        "",
        "> Estas categorias são inferidas somente da assinatura de contas fixas da DFP. "
        "Não equivalem a classificação legal/regulatória.",
        "",
        _markdown_table(cats),
        "",
        "## Frequência de contas fixas",
        f"- Contas semânticas exatas universais: **{len(universais)}**",
        f"- Contas semânticas exatas quase universais (80%–<100% dos empresa-anos): **{len(quase)}**",
        "",
        "## Ambiguidades semânticas",
        f"- Códigos com mais de uma descrição nas 21 FINANCEIRA: **{len(conflitos_cd)}**",
        f"- Descrições normalizadas observadas em mais de um código: **{len(desc_multi_cd)}**",
        "",
        "## Matriz de cobertura dos candidatos",
        "",
        _markdown_table(
            matriz[
                [
                    "INDICADOR_CANDIDATO",
                    "COBERTURA_EMPRESAS_3A_PCT",
                    "N_EMPRESAS_COBERTAS_3A",
                    "STATUS_METODOLOGICO",
                    "LIMITACAO_METODOLOGICA",
                ]
            ]
        ),
        "",
        "## Regra para a próxima etapa",
        "",
        "A ETAPA A mede estrutura e comparabilidade. Cobertura alta não aprova uma fórmula. "
        "A decisão metodológica deve considerar semântica contábil, estabilidade entre companhias "
        "e ausência de ambiguidade de contas antes de qualquer implementação em `src/indicadores.py`.",
    ]

    caminho = SAIDA_DIR / "resumo_financeiras_etapa_a.md"
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho


# ============================================================
# EXECUÇÃO
# ============================================================

def main() -> None:
    print("=" * 78)
    print("SISTEMA CVM — ETAPA A — AUDITORIA ESTRUTURAL FINANCEIRA")
    print("=" * 78)
    print("Modo: SOMENTE LEITURA | Sem implementação de fórmulas novas")
    print()

    df, _empresas_catalogo = carregar_base()

    layouts_anuais = detectar_layouts_anuais(df)
    layouts_fin, companhias = identificar_financeiras(layouts_anuais)

    n_fin = companhias["CD_CVM"].nunique()
    print(f"Companhias FINANCEIRA identificadas: {n_fin}")

    if n_fin != 21:
        print(
            "[ATENÇÃO] O handoff registra 21 companhias FINANCEIRA, "
            f"mas o detector atual encontrou {n_fin}. "
            "O diagnóstico continuará e registrará a divergência."
        )

    cds_fin = set(companhias["CD_CVM"])
    df_fin = df[df["CD_CVM"].isin(cds_fin)].copy()

    assinaturas = construir_assinaturas(
        df_fin=df_fin,
        layouts_fin=layouts_fin,
        companhias=companhias,
    )

    companhias = companhias.merge(
        assinaturas[
            [
                "CD_CVM",
                "CATEGORIA_ESTRUTURAL_DIAGNOSTICA",
            ]
        ],
        on="CD_CVM",
        how="left",
    )

    freq = frequencia_contas(df_fin, companhias)
    conflitos_cd = conflitos_por_codigo(df_fin)
    desc_multi_cd = descricoes_em_multiplos_codigos(df_fin)

    detalhe_conceitos, resumo_conceitos = mapear_conceitos(
        df_fin,
        companhias,
    )
    near_misses = localizar_near_misses(df_fin)

    matriz = matriz_cobertura_candidatos(
        detalhe_conceitos,
        companhias,
    )

    # Subconjuntos de frequência
    universais = freq[
        freq["CLASSE_FREQUENCIA"].eq("UNIVERSAL")
    ].copy()
    quase_universais = freq[
        freq["CLASSE_FREQUENCIA"].eq("QUASE_UNIVERSAL")
    ].copy()

    # Exportações CSV
    salvar_csv(companhias, "01_companhias_financeiras.csv")
    salvar_csv(layouts_fin, "02_layout_por_empresa_ano.csv")
    salvar_csv(assinaturas, "03_assinaturas_estruturais.csv")
    salvar_csv(freq, "04_frequencia_contas_fixas.csv")
    salvar_csv(universais, "05_contas_universais.csv")
    salvar_csv(quase_universais, "06_contas_quase_universais.csv")
    salvar_csv(conflitos_cd, "07_conflitos_descricao_por_codigo.csv")
    salvar_csv(desc_multi_cd, "08_descricoes_em_multiplos_codigos.csv")
    salvar_csv(resumo_conceitos, "09_cobertura_conceitos.csv")
    salvar_csv(detalhe_conceitos, "10_detalhe_conceitos_empresa_ano.csv")
    salvar_csv(near_misses, "11_near_misses_semanticos.csv")
    salvar_csv(matriz, "12_matriz_cobertura_candidatos.csv")

    tabelas = {
        "01_COMPANHIAS": companhias,
        "02_LAYOUT_ANO": layouts_fin,
        "03_ASSINATURAS": assinaturas,
        "04_FREQ_CONTAS": freq,
        "05_UNIVERSAIS": universais,
        "06_QUASE_UNIV": quase_universais,
        "07_CONFLITOS_CD": conflitos_cd,
        "08_DESC_MULTI_CD": desc_multi_cd,
        "09_CONCEITOS": resumo_conceitos,
        "10_DET_CONCEITOS": detalhe_conceitos,
        "11_NEAR_MISSES": near_misses,
        "12_COBERTURA": matriz,
    }

    excel = exportar_excel(tabelas)
    resumo_md = gerar_resumo_markdown(
        companhias=companhias,
        layouts_fin=layouts_fin,
        assinaturas=assinaturas,
        freq=freq,
        matriz=matriz,
        conflitos_cd=conflitos_cd,
        desc_multi_cd=desc_multi_cd,
    )

    print()
    print("COMPANHIAS")
    print("-" * 78)
    print(
        companhias[
            [
                "CD_CVM",
                "DENOM_CIA",
                "CODIGOS_PL",
                "CODIGOS_LL",
                "FINANCEIRA_ESTAVEL_3A",
                "CATEGORIA_ESTRUTURAL_DIAGNOSTICA",
            ]
        ].to_string(index=False)
    )

    print()
    print("MATRIZ DE COBERTURA — SEM CÁLCULO DE INDICADORES NOVOS")
    print("-" * 78)
    print(
        matriz[
            [
                "INDICADOR_CANDIDATO",
                "N_EMPRESAS_COBERTAS_3A",
                "N_EMPRESAS_TOTAL",
                "COBERTURA_EMPRESAS_3A_PCT",
                "STATUS_METODOLOGICO",
            ]
        ].to_string(index=False)
    )

    print()
    print("SAÍDAS")
    print("-" * 78)
    print(f"Pasta: {SAIDA_DIR}")
    print(f"Excel: {excel}")
    print(f"Resumo: {resumo_md}")
    print()
    print(
        "ETAPA A concluída como diagnóstico. "
        "Nenhuma fórmula setorial nova foi implementada."
    )


if __name__ == "__main__":
    main()

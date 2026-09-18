from __future__ import annotations

"""
SISTEMA CVM — ETAPA A.2
Validação semântica e estrutural dos indicadores candidatos para FINANCEIRA.

IMPORTANTE
----------
- SOMENTE LEITURA.
- Não altera app.py.
- Não altera src/indicadores.py.
- Não altera ETL.
- Não altera DuckDB.
- Não implementa indicadores no sistema.
- Apenas corrige o denominador de cobertura e testa a equivalência estrutural
  dos dois sublayouts financeiros observados.
"""

from pathlib import Path
import sys
import re

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

SAIDA_DIR = ROOT_DIR / "data" / "auditoria" / "financeiras_etapa_a2"
SAIDA_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# UTILITÁRIOS
# ============================================================

def _is_conta_fixa(serie: pd.Series) -> pd.Series:
    s = (
        serie.astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )
    return s.isin({"S", "SIM", "1", "TRUE", "T"})


def _normalizar_cd_cvm(serie: pd.Series) -> pd.Series:
    return (
        serie.astype("string")
        .fillna("")
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .str.zfill(6)
    )


def _fmt_lista(valores) -> str:
    itens = sorted(
        {
            str(v).strip()
            for v in valores
            if v is not None
            and not pd.isna(v)
            and str(v).strip()
        }
    )
    return " | ".join(itens)


def _valor_unico(
    g: pd.DataFrame,
    *,
    demonstracao: str,
    codigo: str | None = None,
    descricoes: set[str] | None = None,
) -> tuple[float | None, int, str, str]:
    d = g[g["DEMONSTRACAO"].eq(demonstracao)].copy()

    if codigo is not None:
        d = d[d["CD_CONTA"].eq(codigo)]

    if descricoes is not None:
        alvos = {normalizar_descricao(x) for x in descricoes}
        d = d[d["DS_NORM"].isin(alvos)]

    n = len(d)

    if n != 1:
        return None, n, _fmt_lista(d["CD_CONTA"]), _fmt_lista(d["DS_CONTA"])

    return (
        float(d.iloc[0]["VL_CONTA"]),
        1,
        str(d.iloc[0]["CD_CONTA"]),
        str(d.iloc[0]["DS_CONTA"]),
    )


def _isclose(a, b, rtol=1e-8, atol=1e-6) -> bool:
    if a is None or b is None:
        return False
    if pd.isna(a) or pd.isna(b):
        return False
    return bool(np.isclose(float(a), float(b), rtol=rtol, atol=atol))


def _assinatura(codigo_pl: str | None, codigo_ll: str | None) -> str:
    if codigo_pl == "2.07" and codigo_ll == "3.11":
        return "FIN_207_311"
    if codigo_pl == "2.08" and codigo_ll == "3.09":
        return "FIN_208_309"
    return "FIN_OUTRA_ASSINATURA"


# ============================================================
# CARGA — SOMENTE LEITURA
# ============================================================

def carregar_base() -> pd.DataFrame:
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

    df["CD_CVM"] = _normalizar_cd_cvm(df["CD_CVM"])
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
    df["VL_CONTA"] = pd.to_numeric(df["VL_CONTA"], errors="coerce")

    return df


# ============================================================
# IDENTIFICAÇÃO DOS 51 EMPRESA-ANOS FINANCEIROS
# ============================================================

def identificar_pares_financeiros(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []

    for (cd_cvm, ano), g in df.groupby(["CD_CVM", "ANO"], sort=True):
        bpp = g[g["DEMONSTRACAO"].eq("BPP")][["CD_CONTA", "DS_CONTA"]].copy()
        dre = g[g["DEMONSTRACAO"].eq("DRE")][["CD_CONTA", "DS_CONTA"]].copy()

        layout = detectar_layout(bpp, dre)

        if layout.codigo != LAYOUT_FINANCEIRA:
            continue

        nome = (
            g["DENOM_CIA"].dropna().astype(str).iloc[0]
            if g["DENOM_CIA"].notna().any()
            else ""
        )

        linhas.append(
            {
                "CD_CVM": cd_cvm,
                "DENOM_CIA": nome,
                "ANO": int(ano),
                "CODIGO_PL": layout.codigo_pl,
                "CODIGO_LL": layout.codigo_ll,
                "ASSINATURA": _assinatura(layout.codigo_pl, layout.codigo_ll),
            }
        )

    return (
        pd.DataFrame(linhas)
        .sort_values(["ANO", "DENOM_CIA", "CD_CVM"])
        .reset_index(drop=True)
    )


# ============================================================
# EXTRAÇÃO SEMÂNTICA
# ============================================================

DESC_PL = {"Patrimônio Líquido Consolidado"}

DESC_LL = {
    "Lucro/Prejuízo Consolidado do Período",
    "Lucro ou Prejuízo Líquido Consolidado do Período",
}

DESC_RECEITA_INTERMED = {
    "Receitas de Intermediação Financeira",
    "Receitas da Intermediação Financeira",
}

DESC_DESPESA_INTERMED = {
    "Despesas de Intermediação Financeira",
    "Despesas da Intermediação Financeira",
}

DESC_RBI = {
    "Resultado Bruto de Intermediação Financeira",
    "Resultado Bruto Intermediação Financeira",
}

DESC_RESULTADO_ANTES_TRIBUTOS = {
    "Resultado antes dos Tributos sobre o Lucro",
    "Resultado Antes dos Tributos sobre o Lucro",
}


def auditar_empresa_ano(
    g: pd.DataFrame,
    info: pd.Series,
) -> tuple[dict, list[dict]]:
    d = g[g["CONTA_FIXA"]].copy()

    at, n_at, cd_at, ds_at = _valor_unico(
        d,
        demonstracao="BPA",
        codigo="1",
    )

    pl, n_pl, cd_pl, ds_pl = _valor_unico(
        d,
        demonstracao="BPP",
        descricoes=DESC_PL,
    )

    ll, n_ll, cd_ll, ds_ll = _valor_unico(
        d,
        demonstracao="DRE",
        descricoes=DESC_LL,
    )

    receita_intermed, n_ri, cd_ri, ds_ri = _valor_unico(
        d,
        demonstracao="DRE",
        codigo="3.01",
        descricoes=DESC_RECEITA_INTERMED,
    )

    despesa_intermed, n_di, cd_di, ds_di = _valor_unico(
        d,
        demonstracao="DRE",
        codigo="3.02",
        descricoes=DESC_DESPESA_INTERMED,
    )

    rbi, n_rbi, cd_rbi, ds_rbi = _valor_unico(
        d,
        demonstracao="DRE",
        codigo="3.03",
        descricoes=DESC_RBI,
    )

    rat, n_rat, cd_rat, ds_rat = _valor_unico(
        d,
        demonstracao="DRE",
        codigo="3.05",
        descricoes=DESC_RESULTADO_ANTES_TRIBUTOS,
    )

    passivo_total, n_pt, cd_pt, ds_pt = _valor_unico(
        d,
        demonstracao="BPP",
        codigo="2",
    )

    # Passivos financeiros:
    # somente contas FIXAS de 1º nível abaixo de "2" (2.xx)
    # cuja descrição contenha "PASSIVOS FINANCEIROS".
    bpp = d[d["DEMONSTRACAO"].eq("BPP")].copy()

    pf = bpp[
        bpp["CD_CONTA"].str.match(r"^2\.\d{2}$", na=False)
        & bpp["DS_NORM"].str.contains("PASSIVOS FINANCEIROS", na=False)
    ].copy()

    pf_soma = (
        float(pf["VL_CONTA"].sum())
        if not pf.empty
        else None
    )

    componentes_pf = []

    for _, row in pf.sort_values("CD_CONTA").iterrows():
        componentes_pf.append(
            {
                "CD_CVM": info["CD_CVM"],
                "DENOM_CIA": info["DENOM_CIA"],
                "ANO": int(info["ANO"]),
                "ASSINATURA": info["ASSINATURA"],
                "CD_CONTA": row["CD_CONTA"],
                "DS_CONTA": row["DS_CONTA"],
                "VL_CONTA": row["VL_CONTA"],
            }
        )

    # Soma das contas FIXAS 2.xx para conferir fechamento do Passivo Total.
    top_bpp = bpp[
        bpp["CD_CONTA"].str.match(r"^2\.\d{2}$", na=False)
    ].copy()

    soma_top_bpp = (
        float(top_bpp["VL_CONTA"].sum())
        if not top_bpp.empty
        else None
    )

    esperado_n_pf = (
        2 if info["ASSINATURA"] == "FIN_207_311"
        else 3 if info["ASSINATURA"] == "FIN_208_309"
        else None
    )

    linha = {
        "CD_CVM": info["CD_CVM"],
        "DENOM_CIA": info["DENOM_CIA"],
        "ANO": int(info["ANO"]),
        "ASSINATURA": info["ASSINATURA"],

        "ATIVO_TOTAL": at,
        "N_ATIVO_TOTAL": n_at,
        "CD_ATIVO_TOTAL": cd_at,

        "PL_CONSOLIDADO": pl,
        "N_PL": n_pl,
        "CD_PL_RESOLVIDO": cd_pl,

        "LUCRO_LIQUIDO": ll,
        "N_LL": n_ll,
        "CD_LL_RESOLVIDO": cd_ll,

        "RECEITA_INTERMEDIACAO": receita_intermed,
        "N_RECEITA_INTERMED": n_ri,
        "DS_RECEITA_INTERMED": ds_ri,

        "DESPESA_INTERMEDIACAO": despesa_intermed,
        "N_DESPESA_INTERMED": n_di,
        "DS_DESPESA_INTERMED": ds_di,

        "RESULTADO_BRUTO_INTERMEDIACAO": rbi,
        "N_RBI": n_rbi,
        "DS_RBI": ds_rbi,

        "RESULTADO_ANTES_TRIBUTOS": rat,
        "N_RESULTADO_ANTES_TRIBUTOS": n_rat,

        "PASSIVO_TOTAL": passivo_total,
        "N_PASSIVO_TOTAL": n_pt,

        "N_COMPONENTES_PF": len(pf),
        "N_COMPONENTES_PF_ESPERADO": esperado_n_pf,
        "CODIGOS_PF": _fmt_lista(pf["CD_CONTA"]),
        "DESCRICOES_PF": _fmt_lista(pf["DS_CONTA"]),
        "PASSIVOS_FINANCEIROS_SOMA": pf_soma,

        "N_TOP_BPP": len(top_bpp),
        "SOMA_TOP_BPP": soma_top_bpp,

        "DRE_303_FECHA_301_302": (
            _isclose(rbi, receita_intermed + despesa_intermed)
            if (
                rbi is not None
                and receita_intermed is not None
                and despesa_intermed is not None
            )
            else False
        ),

        "BPP_TOP_FECHA_PASSIVO_TOTAL": (
            _isclose(soma_top_bpp, passivo_total)
            if soma_top_bpp is not None and passivo_total is not None
            else False
        ),

        "PF_COMPONENTES_QTD_OK": (
            len(pf) == esperado_n_pf
            if esperado_n_pf is not None
            else False
        ),
    }

    return linha, componentes_pf


# ============================================================
# COBERTURA CORRIGIDA
# ============================================================

def tabela_cobertura(auditoria: pd.DataFrame) -> pd.DataFrame:
    total = len(auditoria)

    conceitos = [
        ("ATIVO_TOTAL", "N_ATIVO_TOTAL"),
        ("PL_CONSOLIDADO", "N_PL"),
        ("LUCRO_LIQUIDO", "N_LL"),
        ("RECEITA_INTERMEDIACAO_HARMONIZADA", "N_RECEITA_INTERMED"),
        ("DESPESA_INTERMEDIACAO_HARMONIZADA", "N_DESPESA_INTERMED"),
        ("RESULTADO_BRUTO_INTERMEDIACAO_HARMONIZADO", "N_RBI"),
        ("RESULTADO_ANTES_TRIBUTOS", "N_RESULTADO_ANTES_TRIBUTOS"),
        ("PASSIVO_TOTAL", "N_PASSIVO_TOTAL"),
    ]

    linhas = []

    for conceito, coluna_n in conceitos:
        univocos = int(auditoria[coluna_n].eq(1).sum())
        ambiguos = int(auditoria[coluna_n].gt(1).sum())
        ausentes = int(auditoria[coluna_n].eq(0).sum())

        linhas.append(
            {
                "CONCEITO": conceito,
                "EMPRESA_ANOS_DISPONIVEIS": total,
                "PRESENTES_UNIVOCOS": univocos,
                "AMBIGUOS": ambiguos,
                "AUSENTES": ausentes,
                "COBERTURA_CORRIGIDA_PCT": (
                    100 * univocos / total
                    if total
                    else np.nan
                ),
            }
        )

    # Passivos financeiros são uma COMPOSIÇÃO, não uma conta única.
    pf_ok = int(auditoria["PF_COMPONENTES_QTD_OK"].sum())

    linhas.append(
        {
            "CONCEITO": "PASSIVOS_FINANCEIROS_COMPOSICAO_TOP_LEVEL",
            "EMPRESA_ANOS_DISPONIVEIS": total,
            "PRESENTES_UNIVOCOS": pf_ok,
            "AMBIGUOS": 0,
            "AUSENTES": total - pf_ok,
            "COBERTURA_CORRIGIDA_PCT": (
                100 * pf_ok / total
                if total
                else np.nan
            ),
        }
    )

    return pd.DataFrame(linhas)


# ============================================================
# TRANSIÇÕES DE CRESCIMENTO
# ============================================================

def tabela_transicoes(pares: pd.DataFrame) -> pd.DataFrame:
    linhas = []

    conjunto = {
        (str(r.CD_CVM), int(r.ANO))
        for r in pares.itertuples(index=False)
    }

    for ano in [2024, 2025]:
        atuais = {
            cd
            for cd, a in conjunto
            if a == ano
        }

        anteriores = {
            cd
            for cd, a in conjunto
            if a == ano - 1
        }

        comparaveis = sorted(atuais & anteriores)

        linhas.append(
            {
                "ANO_T": ano,
                "ANO_T_MENOS_1": ano - 1,
                "EMPRESAS_ANO_T": len(atuais),
                "EMPRESAS_COM_TRANSICAO": len(comparaveis),
                "COBERTURA_DENTRO_ANO_T_PCT": (
                    100 * len(comparaveis) / len(atuais)
                    if atuais
                    else np.nan
                ),
                "CD_CVM_COM_TRANSICAO": " | ".join(comparaveis),
            }
        )

    return pd.DataFrame(linhas)


# ============================================================
# MATRIZ METODOLÓGICA A.2
# ============================================================

def matriz_candidatos(
    cobertura: pd.DataFrame,
    auditoria: pd.DataFrame,
    transicoes: pd.DataFrame,
) -> pd.DataFrame:
    cov = dict(
        zip(
            cobertura["CONCEITO"],
            cobertura["COBERTURA_CORRIGIDA_PCT"],
        )
    )

    total = len(auditoria)

    dre_fecha = int(auditoria["DRE_303_FECHA_301_302"].sum())
    bpp_fecha = int(auditoria["BPP_TOP_FECHA_PASSIVO_TOTAL"].sum())
    pf_qtd_ok = int(auditoria["PF_COMPONENTES_QTD_OK"].sum())

    crescimento_ok = (
        transicoes["EMPRESAS_COM_TRANSICAO"].sum()
        if not transicoes.empty
        else 0
    )

    linhas = [
        {
            "INDICADOR_CANDIDATO": "ROA",
            "ESTADO": "JÁ APROVADO",
            "COBERTURA_ESTRUTURAL_PCT": min(
                cov.get("ATIVO_TOTAL", 0),
                cov.get("LUCRO_LIQUIDO", 0),
            ),
            "VALIDACAO_A2": "Mantido; A.2 apenas corrige o denominador estrutural.",
            "PROXIMA_DECISAO": "Não alterar nesta fase.",
        },
        {
            "INDICADOR_CANDIDATO": "ROE",
            "ESTADO": "JÁ APROVADO",
            "COBERTURA_ESTRUTURAL_PCT": min(
                cov.get("PL_CONSOLIDADO", 0),
                cov.get("LUCRO_LIQUIDO", 0),
            ),
            "VALIDACAO_A2": "Mantido; A.2 apenas corrige o denominador estrutural.",
            "PROXIMA_DECISAO": "Não alterar nesta fase.",
        },
        {
            "INDICADOR_CANDIDATO": "Patrimônio Líquido / Ativo Total",
            "ESTADO": "CANDIDATO FORTE",
            "COBERTURA_ESTRUTURAL_PCT": min(
                cov.get("PL_CONSOLIDADO", 0),
                cov.get("ATIVO_TOTAL", 0),
            ),
            "VALIDACAO_A2": (
                "PL e Ativo são semanticamente estáveis nos dois sublayouts."
            ),
            "PROXIMA_DECISAO": (
                "Avaliar interpretação como capitalização contábil; "
                "não chamar de capital regulatório/Basileia."
            ),
        },
        {
            "INDICADOR_CANDIDATO": "Passivos Financeiros / Ativo Total",
            "ESTADO": "CANDIDATO CONDICIONAL",
            "COBERTURA_ESTRUTURAL_PCT": min(
                cov.get("PASSIVOS_FINANCEIROS_COMPOSICAO_TOP_LEVEL", 0),
                cov.get("ATIVO_TOTAL", 0),
            ),
            "VALIDACAO_A2": (
                f"{pf_qtd_ok}/{total} empresa-anos com quantidade esperada "
                "de componentes de passivos financeiros; "
                f"{bpp_fecha}/{total} fechamentos do BPP por contas 2.xx."
            ),
            "PROXIMA_DECISAO": (
                "Só aprovar se a soma dos componentes top-level for aceita "
                "metodologicamente como agregado de passivos financeiros."
            ),
        },
        {
            "INDICADOR_CANDIDATO": "Crescimento do Ativo Total",
            "ESTADO": "CANDIDATO FORTE",
            "COBERTURA_ESTRUTURAL_PCT": cov.get("ATIVO_TOTAL", 0),
            "VALIDACAO_A2": (
                f"{crescimento_ok} transições empresa-ano disponíveis "
                "em 2024/2023 e 2025/2024."
            ),
            "PROXIMA_DECISAO": "Usar somente quando houver t e t-1.",
        },
        {
            "INDICADOR_CANDIDATO": "Crescimento do Patrimônio Líquido",
            "ESTADO": "CANDIDATO FORTE",
            "COBERTURA_ESTRUTURAL_PCT": cov.get("PL_CONSOLIDADO", 0),
            "VALIDACAO_A2": (
                f"{crescimento_ok} transições empresa-ano disponíveis "
                "em 2024/2023 e 2025/2024."
            ),
            "PROXIMA_DECISAO": "Usar somente quando houver t e t-1.",
        },
        {
            "INDICADOR_CANDIDATO": "Crescimento do Lucro Líquido",
            "ESTADO": "CANDIDATO COM RESSALVA",
            "COBERTURA_ESTRUTURAL_PCT": cov.get("LUCRO_LIQUIDO", 0),
            "VALIDACAO_A2": (
                f"{crescimento_ok} transições empresa-ano disponíveis."
            ),
            "PROXIMA_DECISAO": (
                "Antes de aprovar, tratar mudança de sinal, prejuízo e base próxima de zero."
            ),
        },
        {
            "INDICADOR_CANDIDATO": "Resultado Bruto da Intermediação / Ativo Médio",
            "ESTADO": "CANDIDATO FORTE",
            "COBERTURA_ESTRUTURAL_PCT": min(
                cov.get("RESULTADO_BRUTO_INTERMEDIACAO_HARMONIZADO", 0),
                cov.get("ATIVO_TOTAL", 0),
            ),
            "VALIDACAO_A2": (
                f"3.03 fecha 3.01 + 3.02 em {dre_fecha}/{total} empresa-anos."
            ),
            "PROXIMA_DECISAO": (
                "Avaliar interpretação econômica; não chamar automaticamente de NIM."
            ),
        },
        {
            "INDICADOR_CANDIDATO": "Resultado Bruto da Intermediação / Receita de Intermediação",
            "ESTADO": "CANDIDATO FORTE COM TESTE DE DENOMINADOR",
            "COBERTURA_ESTRUTURAL_PCT": min(
                cov.get("RESULTADO_BRUTO_INTERMEDIACAO_HARMONIZADO", 0),
                cov.get("RECEITA_INTERMEDIACAO_HARMONIZADA", 0),
            ),
            "VALIDACAO_A2": (
                f"Receita e RBI harmonizados nos dois sublayouts; "
                f"identidade DRE validada em {dre_fecha}/{total}."
            ),
            "PROXIMA_DECISAO": (
                "Testar zeros, sinais e outliers do denominador antes de aprovação."
            ),
        },
        {
            "INDICADOR_CANDIDATO": "Resultado antes dos tributos / Ativo Médio",
            "ESTADO": "CANDIDATO FORTE",
            "COBERTURA_ESTRUTURAL_PCT": min(
                cov.get("RESULTADO_ANTES_TRIBUTOS", 0),
                cov.get("ATIVO_TOTAL", 0),
            ),
            "VALIDACAO_A2": (
                "3.05 é estruturalmente comum nos dois sublayouts."
            ),
            "PROXIMA_DECISAO": (
                "Preferir Ativo Médio, por combinar fluxo com estoque."
            ),
        },
    ]

    return pd.DataFrame(linhas)


# ============================================================
# ALERTAS
# ============================================================

def gerar_alertas(auditoria: pd.DataFrame) -> pd.DataFrame:
    linhas = []

    testes = [
        ("ATIVO_TOTAL_UNICO", auditoria["N_ATIVO_TOTAL"].eq(1)),
        ("PL_UNICO", auditoria["N_PL"].eq(1)),
        ("LL_UNICO", auditoria["N_LL"].eq(1)),
        ("RECEITA_INTERMED_UNICA", auditoria["N_RECEITA_INTERMED"].eq(1)),
        ("DESPESA_INTERMED_UNICA", auditoria["N_DESPESA_INTERMED"].eq(1)),
        ("RBI_UNICO", auditoria["N_RBI"].eq(1)),
        (
            "RESULTADO_ANTES_TRIBUTOS_UNICO",
            auditoria["N_RESULTADO_ANTES_TRIBUTOS"].eq(1),
        ),
        ("PASSIVO_TOTAL_UNICO", auditoria["N_PASSIVO_TOTAL"].eq(1)),
        ("DRE_303_FECHA_301_302", auditoria["DRE_303_FECHA_301_302"]),
        ("BPP_TOP_FECHA_PASSIVO_TOTAL", auditoria["BPP_TOP_FECHA_PASSIVO_TOTAL"]),
        ("PF_COMPONENTES_QTD_OK", auditoria["PF_COMPONENTES_QTD_OK"]),
    ]

    for nome, ok in testes:
        falhas = auditoria.loc[
            ~ok,
            ["CD_CVM", "DENOM_CIA", "ANO", "ASSINATURA"],
        ].copy()

        if falhas.empty:
            linhas.append(
                {
                    "TESTE": nome,
                    "STATUS": "OK",
                    "FALHAS": 0,
                    "CASOS": "",
                }
            )
        else:
            casos = " | ".join(
                f"{r.CD_CVM}-{r.ANO}"
                for r in falhas.itertuples(index=False)
            )
            linhas.append(
                {
                    "TESTE": nome,
                    "STATUS": "REVISAR",
                    "FALHAS": len(falhas),
                    "CASOS": casos,
                }
            )

    return pd.DataFrame(linhas)


# ============================================================
# EXPORTAÇÃO
# ============================================================

def ajustar_largura_planilha(
    writer: pd.ExcelWriter,
    sheet_name: str,
    df: pd.DataFrame,
) -> None:
    ws = writer.sheets[sheet_name]

    for idx, coluna in enumerate(df.columns):
        nome = str(coluna)

        valores = (
            df.iloc[:, idx]
            .head(500)
            .map(lambda x: "" if pd.isna(x) else str(x))
        )

        max_len = max(
            [len(nome)]
            + valores.map(len).tolist()
        )

        ws.set_column(
            idx,
            idx,
            min(max(max_len + 2, 10), 48),
        )

    if len(df.columns) > 0:
        ws.freeze_panes(1, 0)
        ws.autofilter(
            0,
            0,
            max(len(df), 1),
            len(df.columns) - 1,
        )


def exportar_excel(tabelas: dict[str, pd.DataFrame]) -> Path:
    caminho = SAIDA_DIR / "diagnostico_financeiras_etapa_a2.xlsx"

    with pd.ExcelWriter(
        caminho,
        engine="xlsxwriter",
    ) as writer:
        for sheet, df in tabelas.items():
            nome = sheet[:31]
            df.to_excel(
                writer,
                sheet_name=nome,
                index=False,
            )
            ajustar_largura_planilha(
                writer,
                nome,
                df,
            )

    return caminho


def salvar_csvs(tabelas: dict[str, pd.DataFrame]) -> None:
    for nome, df in tabelas.items():
        arquivo = (
            SAIDA_DIR
            / f"{nome.lower()}.csv"
        )
        df.to_csv(
            arquivo,
            index=False,
            encoding="utf-8-sig",
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("=" * 78)
    print("SISTEMA CVM — ETAPA A.2 — VALIDAÇÃO SEMÂNTICA FINANCEIRA")
    print("=" * 78)
    print("Modo: SOMENTE LEITURA | Sem implementação de indicadores no sistema")
    print()

    df = carregar_base()
    pares = identificar_pares_financeiros(df)

    print(f"Empresa-anos FINANCEIRA observados: {len(pares)}")
    print()

    por_ano = (
        pares.groupby("ANO", as_index=False)
        .agg(
            EMPRESA_ANOS=("CD_CVM", "size"),
            EMPRESAS=("CD_CVM", "nunique"),
        )
    )

    assinaturas = (
        pares.groupby(
            ["ANO", "ASSINATURA"],
            as_index=False,
        )
        .agg(
            EMPRESA_ANOS=("CD_CVM", "size"),
            EMPRESAS=("CD_CVM", "nunique"),
        )
    )

    auditoria_linhas = []
    componentes_pf = []

    for info in pares.itertuples(index=False):
        g = df[
            df["CD_CVM"].eq(info.CD_CVM)
            & df["ANO"].eq(info.ANO)
        ].copy()

        info_s = pd.Series(info._asdict())

        linha, componentes = auditar_empresa_ano(
            g,
            info_s,
        )

        auditoria_linhas.append(linha)
        componentes_pf.extend(componentes)

    auditoria = pd.DataFrame(auditoria_linhas)
    componentes_pf = pd.DataFrame(componentes_pf)

    cobertura = tabela_cobertura(auditoria)
    transicoes = tabela_transicoes(pares)
    candidatos = matriz_candidatos(
        cobertura,
        auditoria,
        transicoes,
    )
    alertas = gerar_alertas(auditoria)

    estrutura_pf = (
        auditoria.groupby(
            ["ASSINATURA", "N_COMPONENTES_PF", "CODIGOS_PF", "DESCRICOES_PF"],
            as_index=False,
        )
        .agg(
            EMPRESA_ANOS=("CD_CVM", "size"),
            EMPRESAS=("CD_CVM", "nunique"),
        )
        .sort_values(
            ["ASSINATURA", "EMPRESA_ANOS"],
            ascending=[True, False],
        )
    )

    resumo_validacao = pd.DataFrame(
        [
            {
                "METRICA": "Empresa-anos FINANCEIRA observados",
                "VALOR": len(pares),
            },
            {
                "METRICA": "Empresas FINANCEIRA distintas",
                "VALOR": pares["CD_CVM"].nunique(),
            },
            {
                "METRICA": "FIN_207_311 empresa-anos",
                "VALOR": int(
                    pares["ASSINATURA"]
                    .eq("FIN_207_311")
                    .sum()
                ),
            },
            {
                "METRICA": "FIN_208_309 empresa-anos",
                "VALOR": int(
                    pares["ASSINATURA"]
                    .eq("FIN_208_309")
                    .sum()
                ),
            },
            {
                "METRICA": "DRE 3.03 = 3.01 + 3.02",
                "VALOR": f"{int(auditoria['DRE_303_FECHA_301_302'].sum())}/{len(auditoria)}",
            },
            {
                "METRICA": "BPP contas 2.xx fecham Passivo Total",
                "VALOR": f"{int(auditoria['BPP_TOP_FECHA_PASSIVO_TOTAL'].sum())}/{len(auditoria)}",
            },
            {
                "METRICA": "Passivos financeiros com qtd. de componentes esperada",
                "VALOR": f"{int(auditoria['PF_COMPONENTES_QTD_OK'].sum())}/{len(auditoria)}",
            },
            {
                "METRICA": "Testes com falha",
                "VALOR": int(alertas["STATUS"].ne("OK").sum()),
            },
        ]
    )

    tabelas = {
        "00_RESUMO": resumo_validacao,
        "01_PARES_FIN": pares,
        "02_POR_ANO": por_ano,
        "03_ASSINATURAS": assinaturas,
        "04_AUDITORIA": auditoria,
        "05_COBERTURA": cobertura,
        "06_PF_COMPONENTES": componentes_pf,
        "07_PF_ESTRUTURA": estrutura_pf,
        "08_TRANSICOES": transicoes,
        "09_CANDIDATOS": candidatos,
        "10_ALERTAS": alertas,
    }

    salvar_csvs(tabelas)
    excel = exportar_excel(tabelas)

    print("COBERTURA CORRIGIDA")
    print("-" * 78)
    print(
        cobertura.to_string(index=False)
    )

    print()
    print("SUBLAYOUTS / ASSINATURAS")
    print("-" * 78)
    print(
        assinaturas.to_string(index=False)
    )

    print()
    print("TESTES ESTRUTURAIS")
    print("-" * 78)
    print(
        alertas.to_string(index=False)
    )

    print()
    print("CANDIDATOS — A.2")
    print("-" * 78)
    print(
        candidatos[
            [
                "INDICADOR_CANDIDATO",
                "ESTADO",
                "COBERTURA_ESTRUTURAL_PCT",
                "PROXIMA_DECISAO",
            ]
        ].to_string(index=False)
    )

    print()
    print("SAÍDAS")
    print("-" * 78)
    print(f"Pasta: {SAIDA_DIR}")
    print(f"Excel: {excel}")
    print()
    print(
        "ETAPA A.2 concluída. "
        "Nenhum indicador foi implementado no sistema."
    )


if __name__ == "__main__":
    main()

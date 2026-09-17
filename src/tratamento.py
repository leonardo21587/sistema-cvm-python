from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURAÇÃO
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import (  # noqa: E402
    ANOS_ANALISE,
    DEMONSTRACOES,
    PROCESSED_DIR,
    RAW_DIR,
)

ANOS_ANALISE = tuple(int(ano) for ano in ANOS_ANALISE)
DEMONSTRACOES = tuple(str(dem).upper() for dem in DEMONSTRACOES)


# ============================================================
# ESTRUTURA DA BASE
# ============================================================

COLUNAS_NECESSARIAS = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "CD_CVM",
    "GRUPO_DFP",
    "MOEDA",
    "ESCALA_MOEDA",
    "ORDEM_EXERC",
    "DT_INI_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
    "ST_CONTA_FIXA",
]

# A reapresentação mais recente é selecionada no nível
# companhia + demonstração + exercício econômico.
CHAVE_REAPRESENTACAO = [
    "CD_CVM",
    "DEMONSTRACAO",
    "ANO_EXERCICIO",
]

# Chave final validada empiricamente nos arquivos DFP 2023-2025.
# Para DRE, DT_INI_EXERC distingue o período de fluxo.
# Para BPA/BPP, DT_INI_EXERC é NaT legítimo e dropna=False é usado.
CHAVE_UNICIDADE = [
    "CD_CVM",
    "DEMONSTRACAO",
    "DT_INI_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
]


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================


def remover_acentos(texto: str) -> str:
    texto = str(texto)
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    )


def normalizar_ordem_exerc(serie: pd.Series) -> pd.Series:
    return (
        serie.astype("string")
        .fillna("")
        .map(remover_acentos)
        .str.upper()
        .str.strip()
    )


def salvar_auditoria(df: pd.DataFrame, nome: str) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    caminho = PROCESSED_DIR / nome

    if df.empty:
        if caminho.exists():
            caminho.unlink()
        return caminho

    df.to_csv(
        caminho,
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )
    return caminho


def limpar_artefatos_obsoletos() -> None:
    """Remove artefatos de regras antigas que não fazem parte do ETL atual."""
    obsoletos = [
        "ajustes_anomalias_cvm.csv",
    ]

    for nome in obsoletos:
        caminho = PROCESSED_DIR / nome
        if caminho.exists():
            caminho.unlink()


def localizar_csv(ano: int, demonstracao: str) -> Path:
    demonstracao = str(demonstracao).upper().strip()

    if demonstracao not in DEMONSTRACOES:
        raise ValueError(
            f"Demonstração inválida: {demonstracao}. "
            f"Esperado: {DEMONSTRACOES}"
        )

    caminho = (
        RAW_DIR
        / str(int(ano))
        / f"dfp_cia_aberta_{demonstracao}_con_{int(ano)}.csv"
    )

    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado:\n{caminho}")

    return caminho


# ============================================================
# LEITURA
# ============================================================


def ler_csv_cvm(ano: int, demonstracao: str) -> pd.DataFrame:
    caminho = localizar_csv(ano, demonstracao)
    demonstracao = str(demonstracao).upper().strip()

    print(f"[LEITURA] {ano} | {demonstracao}")

    df = pd.read_csv(
        caminho,
        sep=";",
        encoding="latin1",
        decimal=",",
        dtype={
            "CNPJ_CIA": "string",
            "DENOM_CIA": "string",
            "CD_CVM": "string",
            "GRUPO_DFP": "string",
            "MOEDA": "string",
            "ESCALA_MOEDA": "string",
            "ORDEM_EXERC": "string",
            "CD_CONTA": "string",
            "DS_CONTA": "string",
            "ST_CONTA_FIXA": "string",
        },
        low_memory=False,
    )

    # BPA/BPP podem não possuir DT_INI_EXERC.
    if "DT_INI_EXERC" not in df.columns:
        df["DT_INI_EXERC"] = pd.NaT

    faltantes = [
        coluna for coluna in COLUNAS_NECESSARIAS if coluna not in df.columns
    ]

    if faltantes:
        raise RuntimeError(
            f"{ano} | {demonstracao}: colunas ausentes: {faltantes}"
        )

    df = df[COLUNAS_NECESSARIAS].copy()
    df["ANO_FONTE"] = int(ano)
    df["DEMONSTRACAO"] = demonstracao
    df["ARQUIVO_FONTE"] = caminho.name

    print(f"          {len(df):,} linhas brutas")
    return df


# ============================================================
# PADRONIZAÇÃO
# ============================================================


def padronizar_tipos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    colunas_texto = [
        "CNPJ_CIA",
        "DENOM_CIA",
        "CD_CVM",
        "GRUPO_DFP",
        "MOEDA",
        "ESCALA_MOEDA",
        "ORDEM_EXERC",
        "CD_CONTA",
        "DS_CONTA",
        "ST_CONTA_FIXA",
        "DEMONSTRACAO",
        "ARQUIVO_FONTE",
    ]

    for coluna in colunas_texto:
        if coluna in df.columns:
            df[coluna] = df[coluna].astype("string").str.strip()

    # Identificadores permanecem texto. CD_CVM é canonicamente mantido
    # com 6 posições, preservando zeros à esquerda (ex.: 020125).
    df["CD_CVM"] = (
        df["CD_CVM"]
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .str.zfill(6)
    )

    df["CNPJ_CIA"] = (
        df["CNPJ_CIA"]
        .str.replace(r"\D", "", regex=True)
        .str.zfill(14)
    )

    df["CD_CONTA"] = df["CD_CONTA"].str.strip()

    for coluna in ["DT_REFER", "DT_INI_EXERC", "DT_FIM_EXERC"]:
        df[coluna] = pd.to_datetime(df[coluna], errors="coerce")

    df["VERSAO"] = pd.to_numeric(df["VERSAO"], errors="coerce").astype("Int64")
    df["VL_CONTA"] = pd.to_numeric(df["VL_CONTA"], errors="coerce")
    df["ANO_FONTE"] = pd.to_numeric(
        df["ANO_FONTE"], errors="coerce"
    ).astype("Int64")

    # Ano analítico = exercício econômico, não ano da DFP que o reapresenta.
    df["ANO_EXERCICIO"] = df["DT_FIM_EXERC"].dt.year.astype("Int64")
    df["ANO"] = df["ANO_EXERCICIO"]

    return df


# ============================================================
# MISSING / CONSISTÊNCIA BÁSICA
# ============================================================


def verificar_missing_criticos(df: pd.DataFrame) -> pd.DataFrame:
    colunas_criticas = [
        "CD_CVM",
        "CNPJ_CIA",
        "DENOM_CIA",
        "DT_REFER",
        "DT_FIM_EXERC",
        "ANO_EXERCICIO",
        "VERSAO",
        "CD_CONTA",
        "DS_CONTA",
        "VL_CONTA",
    ]

    linhas = []
    for coluna in colunas_criticas:
        qtd = int(df[coluna].isna().sum())
        linhas.append({"COLUNA": coluna, "MISSING": qtd})

    resumo = pd.DataFrame(linhas)
    problemas = resumo[resumo["MISSING"] > 0].copy()

    salvar_auditoria(problemas, "auditoria_missing_criticos.csv")

    if problemas.empty:
        print("[MISSING] 0 missing nos campos críticos.")
    else:
        print("\n[AVISO] Missing em campos críticos:")
        print(problemas.to_string(index=False))

    # DRE deve possuir DT_INI_EXERC; BPA/BPP podem não possuir.
    dre_sem_inicio = df[
        df["DEMONSTRACAO"].eq("DRE") & df["DT_INI_EXERC"].isna()
    ].copy()
    salvar_auditoria(dre_sem_inicio, "auditoria_dre_sem_dt_ini_exerc.csv")

    if not dre_sem_inicio.empty:
        raise RuntimeError(
            f"Há {len(dre_sem_inicio):,} linhas de DRE sem DT_INI_EXERC."
        )

    return resumo


# ============================================================
# SELEÇÃO DO EXERCÍCIO / REAPRESENTAÇÃO MAIS RECENTE
# ============================================================


def limitar_anos_analise(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()

    mascara = df["ANO_EXERCICIO"].isin(ANOS_ANALISE)
    descartadas = df.loc[~mascara].copy()
    mantidas = df.loc[mascara].copy()

    if not descartadas.empty:
        descartadas["MOTIVO_DESCARTE"] = (
            "Exercício econômico fora de ANOS_ANALISE"
        )

    salvar_auditoria(
        descartadas,
        "auditoria_fora_periodo_descartados.csv",
    )

    print(
        "[ANOS-ALVO] "
        f"{len(df):,} -> {len(mantidas):,} registros"
    )

    if mantidas.empty:
        raise RuntimeError(
            "Nenhum registro permaneceu após limitar ANO_EXERCICIO "
            f"a {ANOS_ANALISE}."
        )

    return mantidas, descartadas


def selecionar_fonte_mais_recente(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()

    if df["ANO_FONTE"].isna().any():
        raise RuntimeError("Há registros com ANO_FONTE inválido ou ausente.")

    max_fonte = df.groupby(
        CHAVE_REAPRESENTACAO,
        dropna=False,
    )["ANO_FONTE"].transform("max")

    mascara_manter = df["ANO_FONTE"].eq(max_fonte)

    descartadas = df.loc[~mascara_manter].copy()
    mantidas = df.loc[mascara_manter].copy()

    if not descartadas.empty:
        descartadas["ANO_FONTE_ESCOLHIDO"] = max_fonte.loc[
            descartadas.index
        ].astype("Int64")
        descartadas["MOTIVO_DESCARTE"] = (
            "Existe DFP posterior apresentando o mesmo exercício econômico"
        )

    caminho = salvar_auditoria(
        descartadas,
        "auditoria_fontes_substituidas.csv",
    )

    print(
        "[FONTE MAIS RECENTE] "
        f"{len(df):,} -> {len(mantidas):,}"
    )

    if not descartadas.empty:
        print(
            f"                      {len(descartadas):,} linhas auditadas em {caminho}"
        )

    return mantidas, descartadas


def manter_maior_versao(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()

    if df["VERSAO"].isna().any():
        quantidade = int(df["VERSAO"].isna().sum())
        raise RuntimeError(
            f"Há {quantidade:,} registros com VERSAO inválida ou ausente."
        )

    max_versao = df.groupby(
        CHAVE_REAPRESENTACAO,
        dropna=False,
    )["VERSAO"].transform("max")

    mascara_manter = df["VERSAO"].eq(max_versao)

    descartadas = df.loc[~mascara_manter].copy()
    mantidas = df.loc[mascara_manter].copy()

    if not descartadas.empty:
        descartadas["VERSAO_ESCOLHIDA"] = max_versao.loc[
            descartadas.index
        ].astype("Int64")
        descartadas["MOTIVO_DESCARTE"] = (
            "Versão anterior da DFP na fonte mais recente selecionada"
        )

    caminho = salvar_auditoria(
        descartadas,
        "auditoria_versoes_descartadas.csv",
    )

    print(
        "[MAIOR VERSÃO] "
        f"{len(df):,} -> {len(mantidas):,}"
    )

    if not descartadas.empty:
        print(
            f"                {len(descartadas):,} linhas auditadas em {caminho}"
        )

    return mantidas, descartadas


# Compatibilidade de nome com comandos antigos de diagnóstico.
# NÃO é usada no ETL final: a seleção correta é por ANO_EXERCICIO +
# fonte mais recente, e não simplesmente ORDEM_EXERC = ÚLTIMO.
def filtrar_ultimo_exercicio(df: pd.DataFrame) -> pd.DataFrame:
    ordem = normalizar_ordem_exerc(df["ORDEM_EXERC"])
    return df.loc[ordem.eq("ULTIMO")].copy()


# Compatibilidade com comandos antigos. No ETL final, usar
# manter_maior_versao() após selecionar_fonte_mais_recente().
def manter_ultima_versao(df: pd.DataFrame) -> pd.DataFrame:
    mantidas, _ = manter_maior_versao(df)
    return mantidas


# ============================================================
# ESCALA MONETÁRIA
# ============================================================


def converter_para_mil_reais(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    escala = (
        df["ESCALA_MOEDA"]
        .fillna("")
        .map(remover_acentos)
        .str.upper()
        .str.strip()
    )

    escalas_encontradas = sorted(escala.unique().tolist())
    print("[ESCALAS] " + ", ".join(escalas_encontradas))

    escalas_permitidas = {"MIL", "UNIDADE"}
    desconhecidas = set(escala.unique()) - escalas_permitidas

    if desconhecidas:
        raise RuntimeError(
            "Escalas monetárias não tratadas: "
            f"{sorted(desconhecidas)}"
        )

    fator = escala.map({"MIL": 1.0, "UNIDADE": 0.001})

    df["VL_CONTA_ORIGINAL"] = df["VL_CONTA"]
    df["VL_CONTA"] = df["VL_CONTA"] * fator
    df["UNIDADE_SISTEMA"] = "R$ mil"

    return df


# ============================================================
# DUPLICATAS EXATAS
# ============================================================


def remover_duplicatas_exatas(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    df = df.copy()

    mascara_remover = df.duplicated(keep="first")
    removidas = df.loc[mascara_remover].copy()

    if not removidas.empty:
        removidas["MOTIVO_DESCARTE"] = "Duplicata 100% idêntica"

    caminho = salvar_auditoria(
        removidas,
        "duplicatas_exatas_removidas.csv",
    )

    df = df.loc[~mascara_remover].copy()

    print(
        "[DUPLICATAS EXATAS] "
        f"{len(removidas):,} linhas removidas."
    )

    if not removidas.empty:
        print(f"                     Auditoria: {caminho}")

    return df, len(removidas)


# ============================================================
# VALIDAÇÕES FINAIS
# ============================================================


def validar_origem_exercicios(df: pd.DataFrame) -> pd.DataFrame:
    resumo = (
        df.groupby(
            [
                "ANO_EXERCICIO",
                "ANO_FONTE",
                "ORDEM_EXERC",
                "DEMONSTRACAO",
            ],
            dropna=False,
        )
        .agg(
            REGISTROS=("CD_CONTA", "size"),
            EMPRESAS=("CD_CVM", "nunique"),
        )
        .reset_index()
        .sort_values(
            [
                "ANO_EXERCICIO",
                "ANO_FONTE",
                "DEMONSTRACAO",
                "ORDEM_EXERC",
            ]
        )
    )

    salvar_auditoria(resumo, "auditoria_origem_exercicios.csv")
    return resumo


def validar_unicidade_final(df: pd.DataFrame) -> None:
    mascara = df.duplicated(
        subset=CHAVE_UNICIDADE,
        keep=False,
    )

    conflitos = (
        df.loc[mascara]
        .sort_values(CHAVE_UNICIDADE)
        .copy()
    )

    caminho = salvar_auditoria(
        conflitos,
        "conflitos_nao_resolvidos.csv",
    )

    if conflitos.empty:
        print("[UNICIDADE FINAL] 0 conflitos.")
        return

    print(
        "[UNICIDADE FINAL] "
        f"{len(conflitos):,} linhas ainda conflitantes."
    )
    print(f"Auditoria: {caminho}")

    raise RuntimeError(
        "Ainda existem conflitos na chave final após selecionar "
        "a reapresentação mais recente, a maior versão e remover "
        "somente duplicatas integralmente idênticas."
    )


# ============================================================
# CATÁLOGO DE EMPRESAS
# ============================================================


def criar_catalogo_empresas(df: pd.DataFrame) -> pd.DataFrame:
    empresas = (
        df[
            [
                "CD_CVM",
                "CNPJ_CIA",
                "DENOM_CIA",
                "ANO",
                "ANO_FONTE",
                "DT_REFER",
            ]
        ]
        .sort_values(
            [
                "CD_CVM",
                "ANO",
                "ANO_FONTE",
                "DT_REFER",
            ]
        )
        .drop_duplicates(subset=["CD_CVM"], keep="last")
        .drop(columns=["ANO", "ANO_FONTE", "DT_REFER"])
        .sort_values(["DENOM_CIA", "CD_CVM"])
        .reset_index(drop=True)
    )

    destino = PROCESSED_DIR / "empresas.parquet"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    empresas.to_parquet(destino, index=False)

    print(
        "[EMPRESAS] "
        f"{len(empresas):,} companhias no catálogo."
    )

    return empresas


# ============================================================
# AUDITORIA RESUMIDA
# ============================================================


def gerar_auditoria(
    df: pd.DataFrame,
    bruto: int,
    candidatos_anos: int,
    apos_fonte: int,
    apos_versao: int,
    fontes_substituidas: int,
    versoes_descartadas: int,
    duplicatas_exatas_removidas: int,
) -> pd.DataFrame:
    resumo_demonstracoes = (
        df.groupby(
            ["ANO", "DEMONSTRACAO"],
            dropna=False,
        )
        .agg(
            REGISTROS=("CD_CONTA", "size"),
            EMPRESAS=("CD_CVM", "nunique"),
            CONTAS=("CD_CONTA", "nunique"),
        )
        .reset_index()
        .sort_values(["ANO", "DEMONSTRACAO"])
    )

    salvar_auditoria(resumo_demonstracoes, "auditoria_etl.csv")

    fluxo = pd.DataFrame(
        [
            {"ETAPA": "Registros brutos nos 9 CSVs", "VALOR": bruto},
            {
                "ETAPA": "Registros dos exercícios 2023-2025",
                "VALOR": candidatos_anos,
            },
            {
                "ETAPA": "Linhas descartadas por existir fonte posterior",
                "VALOR": fontes_substituidas,
            },
            {
                "ETAPA": "Após fonte mais recente",
                "VALOR": apos_fonte,
            },
            {
                "ETAPA": "Linhas descartadas por versão anterior",
                "VALOR": versoes_descartadas,
            },
            {
                "ETAPA": "Após maior VERSAO",
                "VALOR": apos_versao,
            },
            {
                "ETAPA": "Duplicatas exatas removidas",
                "VALOR": duplicatas_exatas_removidas,
            },
            {"ETAPA": "Registros finais", "VALOR": len(df)},
            {
                "ETAPA": "Empresas finais",
                "VALOR": df["CD_CVM"].nunique(),
            },
        ]
    )

    salvar_auditoria(fluxo, "auditoria_fluxo_etl.csv")
    return resumo_demonstracoes


# ============================================================
# ETL PRINCIPAL
# ============================================================


def executar_etl() -> pd.DataFrame:
    print("=" * 70)
    print("SISTEMA CVM - ETL")
    print("=" * 70)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    limpar_artefatos_obsoletos()
    partes: list[pd.DataFrame] = []

    # --------------------------------------------------------
    # 1. Leitura e padronização dos 9 arquivos
    # --------------------------------------------------------
    for ano in ANOS_ANALISE:
        for demonstracao in DEMONSTRACOES:
            parte = ler_csv_cvm(ano, demonstracao)
            parte = padronizar_tipos(parte)
            partes.append(parte)

    base = pd.concat(partes, ignore_index=True)
    bruto = len(base)

    print()
    print(f"[TOTAL BRUTO] {bruto:,} registros.")

    verificar_missing_criticos(base)

    # --------------------------------------------------------
    # 2. Exercícios econômicos do projeto
    # --------------------------------------------------------
    base, _fora_periodo = limitar_anos_analise(base)
    candidatos_anos = len(base)

    # --------------------------------------------------------
    # 3. Reapresentação mais recente disponível
    # --------------------------------------------------------
    base, fontes_descartadas = selecionar_fonte_mais_recente(base)
    apos_fonte = len(base)

    # --------------------------------------------------------
    # 4. Maior versão dentro da fonte escolhida
    # --------------------------------------------------------
    base, versoes_descartadas = manter_maior_versao(base)
    apos_versao = len(base)

    # --------------------------------------------------------
    # 5. Remover somente duplicatas 100% idênticas
    # --------------------------------------------------------
    base, qtd_duplicatas_exatas = remover_duplicatas_exatas(base)

    # --------------------------------------------------------
    # 6. Converter escala monetária para R$ mil
    # --------------------------------------------------------
    base = converter_para_mil_reais(base)

    # --------------------------------------------------------
    # 7. Validações finais
    # --------------------------------------------------------
    validar_unicidade_final(base)
    origem = validar_origem_exercicios(base)

    # --------------------------------------------------------
    # 8. Ordenação final
    # --------------------------------------------------------
    base = (
        base.sort_values(
            [
                "CD_CVM",
                "ANO",
                "DEMONSTRACAO",
                "DT_INI_EXERC",
                "DT_FIM_EXERC",
                "CD_CONTA",
            ],
            na_position="first",
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # 9. Parquet principal
    # --------------------------------------------------------
    ano_inicial = min(ANOS_ANALISE)
    ano_final = max(ANOS_ANALISE)

    destino = PROCESSED_DIR / f"dfp_{ano_inicial}_{ano_final}.parquet"
    base.to_parquet(destino, index=False)

    # --------------------------------------------------------
    # 10. Catálogo de empresas
    # --------------------------------------------------------
    criar_catalogo_empresas(base)

    # --------------------------------------------------------
    # 11. Auditoria
    # --------------------------------------------------------
    auditoria = gerar_auditoria(
        df=base,
        bruto=bruto,
        candidatos_anos=candidatos_anos,
        apos_fonte=apos_fonte,
        apos_versao=apos_versao,
        fontes_substituidas=len(fontes_descartadas),
        versoes_descartadas=len(versoes_descartadas),
        duplicatas_exatas_removidas=qtd_duplicatas_exatas,
    )

    # --------------------------------------------------------
    # 12. Resultado
    # --------------------------------------------------------
    print()
    print("=" * 70)
    print("ETL CONCLUÍDO COM SUCESSO")
    print("=" * 70)
    print(f"Registros finais: {len(base):,}")
    print(f"Empresas únicas: {base['CD_CVM'].nunique():,}")
    print(
        "Fontes anteriores substituídas: "
        f"{len(fontes_descartadas):,} linhas"
    )
    print(
        "Versões anteriores descartadas: "
        f"{len(versoes_descartadas):,} linhas"
    )
    print(
        "Duplicatas exatas removidas: "
        f"{qtd_duplicatas_exatas:,}"
    )
    print()
    print("Arquivo principal:")
    print(destino)
    print()
    print("Origem dos exercícios:")
    print(origem.to_string(index=False))
    print()
    print("Resumo por ano e demonstração:")
    print(auditoria.to_string(index=False))

    return base


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    executar_etl()

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import ANOS_ANALISE, PROCESSED_DIR
from src.tratamento import (
    converter_para_mil_reais,
    ler_csv_cvm,
    padronizar_tipos,
    remover_acentos,
)


ANO_BASE = min(ANOS_ANALISE)
ANO_AUXILIAR = ANO_BASE - 1

DESTINO = (
    PROCESSED_DIR
    / f"saldos_auxiliares_{ANO_AUXILIAR}.parquet"
)

DESTINO_AUDITORIA = (
    PROCESSED_DIR
    / f"auditoria_saldos_auxiliares_{ANO_AUXILIAR}.csv"
)

DESTINO_CONFLITOS = (
    PROCESSED_DIR
    / f"conflitos_saldos_auxiliares_{ANO_AUXILIAR}.csv"
)


CONTAS_NECESSARIAS = {
    "BPA": {"1"},      # Ativo Total
    "BPP": {"2.03"},   # Patrimônio Líquido
}


def _normalizar_ordem(serie: pd.Series) -> pd.Series:
    return (
        serie
        .fillna("")
        .map(remover_acentos)
        .str.upper()
        .str.strip()
    )


def _carregar_demonstracao_auxiliar(
    demonstracao: str,
) -> pd.DataFrame:
    """
    Usa a DFP do primeiro ano exibido (2023) para recuperar
    o comparativo do ano anterior (2022), necessário às médias
    de Ativo e Patrimônio Líquido.
    """
    df = ler_csv_cvm(
        ANO_BASE,
        demonstracao,
    )

    df = padronizar_tipos(df)

    df["ANO_EXERCICIO"] = (
        df["DT_FIM_EXERC"]
        .dt.year
        .astype("Int64")
    )

    ordem = _normalizar_ordem(
        df["ORDEM_EXERC"]
    )

    df = df[
        df["ANO_EXERCICIO"].eq(
            ANO_AUXILIAR
        )
        & ordem.eq("PENULTIMO")
    ].copy()

    if df.empty:
        raise RuntimeError(
            f"Nenhum saldo auxiliar de {ANO_AUXILIAR} "
            f"foi encontrado em {demonstracao} da DFP "
            f"{ANO_BASE}."
        )

    if df["VERSAO"].isna().any():
        raise RuntimeError(
            f"VERSAO ausente/inválida em {demonstracao} "
            f"para o ano auxiliar."
        )

    grupo_versao = [
        "CD_CVM",
        "DEMONSTRACAO",
        "ANO_EXERCICIO",
    ]

    versao_maxima = df.groupby(
        grupo_versao,
        dropna=False,
    )["VERSAO"].transform("max")

    df = df[
        df["VERSAO"].eq(
            versao_maxima
        )
    ].copy()

    df = converter_para_mil_reais(df)

    df = df[
        df["CD_CONTA"].isin(
            CONTAS_NECESSARIAS[
                demonstracao
            ]
        )
    ].copy()

    return df


def construir_saldos_auxiliares() -> pd.DataFrame:
    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    partes = [
        _carregar_demonstracao_auxiliar("BPA"),
        _carregar_demonstracao_auxiliar("BPP"),
    ]

    base = pd.concat(
        partes,
        ignore_index=True,
    )

    antes_duplicatas = len(base)

    base = (
        base
        .drop_duplicates()
        .copy()
    )

    duplicatas_exatas = (
        antes_duplicatas - len(base)
    )

    chave = [
        "CD_CVM",
        "DEMONSTRACAO",
        "ANO_EXERCICIO",
        "CD_CONTA",
    ]

    # Duplicidades econômicas:
    # se a mesma chave aparece mais de uma vez com o MESMO VL_CONTA,
    # as linhas são equivalentes para o saldo contábil necessário.
    # Preservamos uma linha e auditamos as demais.
    duplicadas_chave = base[
        base.duplicated(
            subset=chave,
            keep=False,
        )
    ].copy()

    if not duplicadas_chave.empty:
        diagnostico = (
            duplicadas_chave
            .groupby(
                chave,
                dropna=False,
            )
            .agg(
                N_LINHAS=("VL_CONTA", "size"),
                N_VALORES=("VL_CONTA", "nunique"),
                VL_MIN=("VL_CONTA", "min"),
                VL_MAX=("VL_CONTA", "max"),
            )
            .reset_index()
        )

        chaves_conflitantes = diagnostico[
            diagnostico["N_VALORES"] > 1
        ][chave]

        if not chaves_conflitantes.empty:
            conflitos = duplicadas_chave.merge(
                chaves_conflitantes,
                on=chave,
                how="inner",
            )

            conflitos.to_csv(
                DESTINO_CONFLITOS,
                index=False,
                sep=";",
                encoding="utf-8-sig",
            )

            raise RuntimeError(
                "Existem conflitos reais nos saldos auxiliares "
                "(mesma chave com valores diferentes). "
                f"Auditoria: {DESTINO_CONFLITOS}"
            )

        # Mesma chave e mesmo valor: colapsa de forma determinística.
        base = (
            base.sort_values(
                chave
                + [
                    "DT_REFER",
                    "VERSAO",
                ]
            )
            .drop_duplicates(
                subset=chave,
                keep="last",
            )
            .copy()
        )

    if DESTINO_CONFLITOS.exists():
        DESTINO_CONFLITOS.unlink()

    colunas_saida = [
        "CD_CVM",
        "CNPJ_CIA",
        "DENOM_CIA",
        "ANO_EXERCICIO",
        "ANO_FONTE",
        "VERSAO",
        "ORDEM_EXERC",
        "DEMONSTRACAO",
        "CD_CONTA",
        "DS_CONTA",
        "VL_CONTA",
        "UNIDADE_SISTEMA",
    ]

    base = (
        base[colunas_saida]
        .sort_values(
            [
                "CD_CVM",
                "DEMONSTRACAO",
                "CD_CONTA",
            ]
        )
        .reset_index(drop=True)
    )

    base.to_parquet(
        DESTINO,
        index=False,
    )

    auditoria = (
        base.groupby(
            [
                "ANO_EXERCICIO",
                "DEMONSTRACAO",
                "CD_CONTA",
            ],
            dropna=False,
        )
        .agg(
            REGISTROS=("CD_CVM", "size"),
            EMPRESAS=("CD_CVM", "nunique"),
        )
        .reset_index()
    )

    auditoria["DUPLICATAS_EXATAS_REMOVIDAS"] = (
        duplicatas_exatas
    )

    auditoria.to_csv(
        DESTINO_AUDITORIA,
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )

    return base


def main() -> None:
    print("=" * 70)
    print("SISTEMA CVM - SALDOS AUXILIARES")
    print("=" * 70)

    base = construir_saldos_auxiliares()

    print()
    print(
        f"Ano auxiliar: {ANO_AUXILIAR}"
    )
    print(
        f"Registros finais: {len(base):,}"
    )
    print(
        f"Empresas com Ativo Total: "
        f"{base.loc[base['CD_CONTA'].eq('1'), 'CD_CVM'].nunique():,}"
    )
    print(
        f"Empresas com Patrimônio Líquido: "
        f"{base.loc[base['CD_CONTA'].eq('2.03'), 'CD_CVM'].nunique():,}"
    )
    print()
    print("Arquivo:")
    print(DESTINO)

    print()
    print("AUDITORIA:")
    print(
        base.groupby(
            ["DEMONSTRACAO", "CD_CONTA"],
            dropna=False,
        )
        .agg(
            REGISTROS=("CD_CVM", "size"),
            EMPRESAS=("CD_CVM", "nunique"),
        )
        .reset_index()
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()

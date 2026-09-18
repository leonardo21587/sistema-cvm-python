from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from config.settings import (
    ANOS_ANALISE,
    PROCESSED_DIR,
)

from src.tratamento import (
    converter_para_mil_reais,
    ler_csv_cvm,
    padronizar_tipos,
    remover_acentos,
)


ANO_BASE = min(
    ANOS_ANALISE
)

ANO_AUXILIAR = (
    ANO_BASE
    - 1
)


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


def _normalizar_ordem(
    serie: pd.Series,
) -> pd.Series:

    return (
        serie
        .fillna("")
        .map(
            remover_acentos
        )
        .str.upper()
        .str.strip()
    )


def _normalizar_descricao(
    serie: pd.Series,
) -> pd.Series:

    return (
        serie
        .fillna("")
        .map(
            remover_acentos
        )
        .str.upper()
        .str.strip()
        .str.replace(
            r"\s+",
            " ",
            regex=True,
        )
    )


def _carregar_demonstracao_auxiliar(
    demonstracao: str,
) -> pd.DataFrame:

    df = ler_csv_cvm(
        ANO_BASE,
        demonstracao,
    )

    df = padronizar_tipos(
        df
    )

    df[
        "ANO_EXERCICIO"
    ] = (
        df[
            "DT_FIM_EXERC"
        ]
        .dt.year
        .astype(
            "Int64"
        )
    )

    ordem = (
        _normalizar_ordem(
            df[
                "ORDEM_EXERC"
            ]
        )
    )

    df = df[
        df[
            "ANO_EXERCICIO"
        ].eq(
            ANO_AUXILIAR
        )
        & ordem.eq(
            "PENULTIMO"
        )
    ].copy()

    if df.empty:

        raise RuntimeError(
            "Nenhum saldo auxiliar de "
            f"{ANO_AUXILIAR} foi encontrado "
            f"em {demonstracao} da DFP "
            f"{ANO_BASE}."
        )

    if df[
        "VERSAO"
    ].isna().any():

        raise RuntimeError(
            "VERSAO ausente/inválida "
            f"em {demonstracao} "
            "para o ano auxiliar."
        )

    grupo_versao = [
        "CD_CVM",
        "DEMONSTRACAO",
        "ANO_EXERCICIO",
    ]

    versao_maxima = (
        df.groupby(
            grupo_versao,
            dropna=False,
        )[
            "VERSAO"
        ]
        .transform(
            "max"
        )
    )

    df = df[
        df[
            "VERSAO"
        ].eq(
            versao_maxima
        )
    ].copy()

    df = converter_para_mil_reais(
        df
    )

    if demonstracao == "BPA":

        df = df[
            df[
                "CD_CONTA"
            ]
            .astype(str)
            .str.strip()
            .eq("1")
        ].copy()

    elif demonstracao == "BPP":

        descricao = (
            _normalizar_descricao(
                df[
                    "DS_CONTA"
                ]
            )
        )

        df = df[
            descricao.eq(
                "PATRIMONIO LIQUIDO CONSOLIDADO"
            )
        ].copy()

    else:

        raise ValueError(
            "Demonstracao auxiliar deve "
            "ser BPA ou BPP."
        )

    return df


def construir_saldos_auxiliares() -> pd.DataFrame:

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    partes = [
        _carregar_demonstracao_auxiliar(
            "BPA"
        ),
        _carregar_demonstracao_auxiliar(
            "BPP"
        ),
    ]

    base = pd.concat(
        partes,
        ignore_index=True,
    )

    antes_duplicatas = len(
        base
    )

    base = (
        base
        .drop_duplicates()
        .copy()
    )

    duplicatas_exatas = (
        antes_duplicatas
        - len(
            base
        )
    )

    chave = [
        "CD_CVM",
        "DEMONSTRACAO",
        "ANO_EXERCICIO",
        "CD_CONTA",
    ]

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
                N_LINHAS=(
                    "VL_CONTA",
                    "size",
                ),
                N_VALORES=(
                    "VL_CONTA",
                    "nunique",
                ),
                VL_MIN=(
                    "VL_CONTA",
                    "min",
                ),
                VL_MAX=(
                    "VL_CONTA",
                    "max",
                ),
            )
            .reset_index()
        )

        chaves_conflitantes = (
            diagnostico[
                diagnostico[
                    "N_VALORES"
                ]
                > 1
            ][
                chave
            ]
        )

        if not chaves_conflitantes.empty:

            conflitos = (
                duplicadas_chave
                .merge(
                    chaves_conflitantes,
                    on=chave,
                    how="inner",
                )
            )

            conflitos.to_csv(
                DESTINO_CONFLITOS,
                index=False,
                sep=";",
                encoding="utf-8-sig",
            )

            raise RuntimeError(
                "Existem conflitos reais "
                "nos saldos auxiliares "
                "(mesma chave com valores diferentes). "
                f"Auditoria: {DESTINO_CONFLITOS}"
            )

        base = (
            base
            .sort_values(
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
        base[
            colunas_saida
        ]
        .sort_values(
            [
                "CD_CVM",
                "DEMONSTRACAO",
                "CD_CONTA",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # Garantia semântica:
    # cada empresa deve ter no máximo um Ativo Total e um
    # Patrimônio Líquido Consolidado para o ano auxiliar.
    contagem_empresa = (
        base.groupby(
            [
                "CD_CVM",
                "DEMONSTRACAO",
            ],
            dropna=False,
        )
        .size()
        .reset_index(
            name="N"
        )
    )

    problemas = (
        contagem_empresa[
            contagem_empresa[
                "N"
            ]
            > 1
        ]
    )

    if not problemas.empty:

        raise RuntimeError(
            "Mais de uma conta auxiliar principal "
            "foi encontrada para a mesma "
            "empresa/demonstração."
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
                "DS_CONTA",
            ],
            dropna=False,
        )
        .agg(
            REGISTROS=(
                "CD_CVM",
                "size",
            ),
            EMPRESAS=(
                "CD_CVM",
                "nunique",
            ),
        )
        .reset_index()
    )

    auditoria[
        "DUPLICATAS_EXATAS_REMOVIDAS"
    ] = duplicatas_exatas

    auditoria.to_csv(
        DESTINO_AUDITORIA,
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )

    return base


def main() -> None:

    print(
        "="
        * 70
    )

    print(
        "SISTEMA CVM - SALDOS AUXILIARES"
    )

    print(
        "="
        * 70
    )

    base = (
        construir_saldos_auxiliares()
    )

    print()

    print(
        f"Ano auxiliar: "
        f"{ANO_AUXILIAR}"
    )

    print(
        "Registros finais: "
        f"{len(base):,}"
    )

    empresas_at = (
        base.loc[
            (
                base[
                    "DEMONSTRACAO"
                ]
                == "BPA"
            )
            & (
                base[
                    "CD_CONTA"
                ]
                .astype(str)
                .str.strip()
                .eq("1")
            ),
            "CD_CVM",
        ]
        .nunique()
    )

    empresas_pl = (
        base.loc[
            (
                base[
                    "DEMONSTRACAO"
                ]
                == "BPP"
            )
            & (
                _normalizar_descricao(
                    base[
                        "DS_CONTA"
                    ]
                )
                .eq(
                    "PATRIMONIO LIQUIDO CONSOLIDADO"
                )
            ),
            "CD_CVM",
        ]
        .nunique()
    )

    print(
        "Empresas com Ativo Total: "
        f"{empresas_at:,}"
    )

    print(
        "Empresas com Patrimônio Líquido: "
        f"{empresas_pl:,}"
    )

    print()

    print(
        "Arquivo:"
    )

    print(
        DESTINO
    )

    print()

    print(
        "AUDITORIA:"
    )

    print(
        base.groupby(
            [
                "DEMONSTRACAO",
                "CD_CONTA",
                "DS_CONTA",
            ],
            dropna=False,
        )
        .agg(
            REGISTROS=(
                "CD_CVM",
                "size",
            ),
            EMPRESAS=(
                "CD_CVM",
                "nunique",
            ),
        )
        .reset_index()
        .to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()

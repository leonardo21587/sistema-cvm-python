from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.demonstracoes import montar_quadro_demonstracao


BASE_AV = {
    "BPA": "1",      # Ativo Total
    "BPP": "2",      # Passivo Total
    "DRE": "3.01",   # Receita de Venda de Bens e/ou Serviços
}


def _anos_no_quadro(df: pd.DataFrame) -> list[int]:
    return sorted(
        coluna
        for coluna in df.columns
        if isinstance(coluna, int)
    )


def calcular_analise_vertical(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
) -> pd.DataFrame:
    """
    Calcula AV por exercício.

    BPA: cada conta / Ativo Total (1)
    BPP: cada conta / Passivo Total (2)
    DRE: cada conta / Receita de Venda de Bens e/ou Serviços (3.01)

    O retorno mantém os valores originais em R$ mil e adiciona
    colunas AV_<ano> em percentual.
    """
    demonstracao = demonstracao.upper().strip()

    if demonstracao not in BASE_AV:
        raise ValueError(
            "DEMONSTRACAO deve ser BPA, BPP ou DRE."
        )

    quadro = montar_quadro_demonstracao(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=anos,
        somente_contas_fixas=somente_contas_fixas,
    )

    if quadro.empty:
        return quadro

    conta_base = BASE_AV[demonstracao]

    linha_base = quadro[
        quadro["CD_CONTA"].astype(str).eq(conta_base)
    ]

    if len(linha_base) != 1:
        raise RuntimeError(
            f"Conta-base da AV não encontrada de forma única: "
            f"{demonstracao} | conta {conta_base}"
        )

    resultado = quadro.copy()
    anos_quadro = _anos_no_quadro(resultado)

    for ano in anos_quadro:
        denominador = linha_base.iloc[0][ano]

        if pd.isna(denominador):
            resultado[f"AV_{ano}"] = pd.NA
            continue

        denominador = float(denominador)

        if denominador == 0:
            resultado[f"AV_{ano}"] = pd.NA
            continue

        resultado[f"AV_{ano}"] = (
            pd.to_numeric(
                resultado[ano],
                errors="coerce",
            )
            / denominador
            * 100.0
        )

    return resultado


def quadro_av_apresentacao(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
) -> pd.DataFrame:
    """
    Organiza valor e AV lado a lado por exercício.
    """
    df = calcular_analise_vertical(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=anos,
        somente_contas_fixas=somente_contas_fixas,
    )

    if df.empty:
        return df

    anos_quadro = _anos_no_quadro(df)

    colunas = [
        "CD_CONTA",
        "DS_CONTA",
    ]

    for ano in anos_quadro:
        colunas.extend(
            [
                ano,
                f"AV_{ano}",
            ]
        )

    return df[colunas].copy()

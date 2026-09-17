from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.demonstracoes import montar_quadro_demonstracao


def _anos_no_quadro(df: pd.DataFrame) -> list[int]:
    return sorted(
        coluna
        for coluna in df.columns
        if isinstance(coluna, int)
    )


def calcular_analise_horizontal(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
    ano_base: int | None = None,
) -> pd.DataFrame:
    """
    Calcula Análise Horizontal (AH) para BPA, BPP ou DRE.

    São produzidas duas medidas:

    1. AH_IND_<ano>
       Índice com ano-base = 100:
           valor_ano / valor_ano_base * 100

    2. AH_VAR_<ano>
       Variação percentual acumulada em relação ao ano-base:
           (valor_ano / valor_ano_base - 1) * 100

    Regras:
    - ano-base padrão: menor exercício disponível;
    - ano-base recebe AH_IND = 100 e AH_VAR = 0 quando o valor-base
      é diferente de zero;
    - se o valor do ano-base for zero ou missing, a AH daquela conta
      fica missing (N/D na futura interface), evitando divisão por zero;
    - valores negativos são preservados conforme a demonstração original.
    """
    demonstracao = demonstracao.upper().strip()

    if demonstracao not in {"BPA", "BPP", "DRE"}:
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

    resultado = quadro.copy()
    anos_quadro = _anos_no_quadro(resultado)

    if not anos_quadro:
        return resultado

    if ano_base is None:
        ano_base = anos_quadro[0]
    else:
        ano_base = int(ano_base)

    if ano_base not in anos_quadro:
        raise ValueError(
            f"Ano-base {ano_base} não está entre os anos disponíveis: "
            f"{anos_quadro}"
        )

    base = pd.to_numeric(
        resultado[ano_base],
        errors="coerce",
    )

    base_valida = base.notna() & base.ne(0)

    for ano in anos_quadro:
        atual = pd.to_numeric(
            resultado[ano],
            errors="coerce",
        )

        indice = pd.Series(
            pd.NA,
            index=resultado.index,
            dtype="Float64",
        )

        variacao = pd.Series(
            pd.NA,
            index=resultado.index,
            dtype="Float64",
        )

        mascara = base_valida & atual.notna()

        indice.loc[mascara] = (
            atual.loc[mascara]
            / base.loc[mascara]
            * 100.0
        )

        variacao.loc[mascara] = (
            atual.loc[mascara]
            / base.loc[mascara]
            - 1.0
        ) * 100.0

        resultado[f"AH_IND_{ano}"] = indice
        resultado[f"AH_VAR_{ano}"] = variacao

    resultado.attrs["ANO_BASE_AH"] = ano_base

    return resultado


def quadro_ah_apresentacao(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
    ano_base: int | None = None,
) -> pd.DataFrame:
    """
    Organiza valor, índice AH e variação AH lado a lado por exercício.
    """
    df = calcular_analise_horizontal(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=anos,
        somente_contas_fixas=somente_contas_fixas,
        ano_base=ano_base,
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
                f"AH_IND_{ano}",
                f"AH_VAR_{ano}",
            ]
        )

    return df[colunas].copy()


def calcular_variacao_ano_a_ano(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
) -> pd.DataFrame:
    """
    Calcula também a variação percentual entre exercícios consecutivos.

    Exemplo:
        VAR_2024_vs_2023
        VAR_2025_vs_2024

    Se o valor do ano anterior for zero ou missing, retorna missing.
    """
    quadro = montar_quadro_demonstracao(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=anos,
        somente_contas_fixas=somente_contas_fixas,
    )

    if quadro.empty:
        return quadro

    resultado = quadro.copy()
    anos_quadro = _anos_no_quadro(resultado)

    for anterior, atual in zip(
        anos_quadro[:-1],
        anos_quadro[1:],
    ):
        valor_anterior = pd.to_numeric(
            resultado[anterior],
            errors="coerce",
        )

        valor_atual = pd.to_numeric(
            resultado[atual],
            errors="coerce",
        )

        mascara = (
            valor_anterior.notna()
            & valor_anterior.ne(0)
            & valor_atual.notna()
        )

        coluna = pd.Series(
            pd.NA,
            index=resultado.index,
            dtype="Float64",
        )

        coluna.loc[mascara] = (
            valor_atual.loc[mascara]
            / valor_anterior.loc[mascara]
            - 1.0
        ) * 100.0

        resultado[
            f"VAR_{atual}_vs_{anterior}"
        ] = coluna

    return resultado

from __future__ import annotations

from typing import Iterable

import pandas as pd

from src.banco import anos_disponiveis, carregar_demonstracao


DEMONSTRACOES_VALIDAS = {"BPA", "BPP", "DRE"}


def _normalizar_cd_cvm(cd_cvm: str) -> str:
    return str(cd_cvm).strip().zfill(6)


def _chave_ordenacao_conta(codigo: str) -> tuple:
    """
    Ordena códigos contábeis hierarquicamente.
    Ex.: 1 < 1.01 < 1.01.01 < 1.02
    """
    partes = str(codigo).strip().split(".")
    chave = []

    for parte in partes:
        try:
            chave.append((0, int(parte)))
        except ValueError:
            chave.append((1, parte))

    return tuple(chave)


def carregar_serie_demonstracao(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
) -> pd.DataFrame:
    """
    Carrega uma demonstração para vários exercícios e devolve
    as observações em formato longo, preservando metadados de origem.
    """
    cd_cvm = _normalizar_cd_cvm(cd_cvm)
    demonstracao = demonstracao.upper().strip()

    if demonstracao not in DEMONSTRACOES_VALIDAS:
        raise ValueError(
            "DEMONSTRACAO deve ser BPA, BPP ou DRE."
        )

    disponiveis = anos_disponiveis(cd_cvm)

    if anos is None:
        anos_selecionados = disponiveis
    else:
        anos_selecionados = sorted(
            {
                int(ano)
                for ano in anos
                if int(ano) in disponiveis
            }
        )

    if not anos_selecionados:
        return pd.DataFrame()

    partes: list[pd.DataFrame] = []

    for ano in anos_selecionados:
        d = carregar_demonstracao(
            cd_cvm=cd_cvm,
            ano=ano,
            demonstracao=demonstracao,
        ).copy()

        if somente_contas_fixas:
            d = d[
                d["ST_CONTA_FIXA"]
                .astype("string")
                .str.strip()
                .str.upper()
                .eq("S")
            ].copy()

        partes.append(d)

    if not partes:
        return pd.DataFrame()

    base = pd.concat(
        partes,
        ignore_index=True,
    )

    base["_ordem_conta"] = base["CD_CONTA"].map(
        _chave_ordenacao_conta
    )

    base = (
        base.sort_values(
            ["_ordem_conta", "ANO"]
        )
        .drop(columns="_ordem_conta")
        .reset_index(drop=True)
    )

    return base


def montar_quadro_demonstracao(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
) -> pd.DataFrame:
    """
    Converte a demonstração para formato de apresentação:
    uma linha por conta e uma coluna de valor para cada exercício.
    """
    base = carregar_serie_demonstracao(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=anos,
        somente_contas_fixas=somente_contas_fixas,
    )

    if base.empty:
        return pd.DataFrame()

    # Usa a descrição mais recente disponível para cada código.
    descricoes = (
        base.sort_values(
            ["CD_CONTA", "ANO"]
        )
        .drop_duplicates(
            subset=["CD_CONTA"],
            keep="last",
        )[
            ["CD_CONTA", "DS_CONTA"]
        ]
    )

    valores = (
        base.pivot(
            index="CD_CONTA",
            columns="ANO",
            values="VL_CONTA",
        )
        .reset_index()
    )

    quadro = descricoes.merge(
        valores,
        on="CD_CONTA",
        how="right",
        validate="one_to_one",
    )

    quadro["_ordem_conta"] = quadro["CD_CONTA"].map(
        _chave_ordenacao_conta
    )

    quadro = (
        quadro.sort_values("_ordem_conta")
        .drop(columns="_ordem_conta")
        .reset_index(drop=True)
    )

    quadro.columns.name = None

    return quadro


def montar_bp_completo(
    cd_cvm: str,
    anos: Iterable[int] | None = None,
    somente_contas_fixas: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Retorna BP Ativo e BP Passivo em quadros separados.
    """
    ativo = montar_quadro_demonstracao(
        cd_cvm=cd_cvm,
        demonstracao="BPA",
        anos=anos,
        somente_contas_fixas=somente_contas_fixas,
    )

    passivo = montar_quadro_demonstracao(
        cd_cvm=cd_cvm,
        demonstracao="BPP",
        anos=anos,
        somente_contas_fixas=somente_contas_fixas,
    )

    return ativo, passivo


def obter_metadados_fontes(
    cd_cvm: str,
    demonstracao: str,
    anos: Iterable[int] | None = None,
) -> pd.DataFrame:
    """
    Resume a origem da informação exibida para auditoria.
    """
    base = carregar_serie_demonstracao(
        cd_cvm=cd_cvm,
        demonstracao=demonstracao,
        anos=anos,
        somente_contas_fixas=False,
    )

    if base.empty:
        return pd.DataFrame()

    colunas = [
        "ANO",
        "ANO_FONTE",
        "VERSAO",
        "ORDEM_EXERC",
        "DT_REFER",
        "DT_INI_EXERC",
        "DT_FIM_EXERC",
    ]

    return (
        base[colunas]
        .drop_duplicates()
        .sort_values(["ANO", "ANO_FONTE", "VERSAO"])
        .reset_index(drop=True)
    )


def resumo_empresa(
    cd_cvm: str,
    anos: Iterable[int] | None = None,
) -> dict[str, object]:
    """
    Resumo estrutural rápido para testes e interface.
    """
    cd_cvm = _normalizar_cd_cvm(cd_cvm)
    disponiveis = anos_disponiveis(cd_cvm)

    if anos is None:
        anos_usados = disponiveis
    else:
        anos_usados = sorted(
            {
                int(a)
                for a in anos
                if int(a) in disponiveis
            }
        )

    resultado: dict[str, object] = {
        "CD_CVM": cd_cvm,
        "ANOS_DISPONIVEIS": disponiveis,
        "ANOS_USADOS": anos_usados,
    }

    for dem in ["BPA", "BPP", "DRE"]:
        base = carregar_serie_demonstracao(
            cd_cvm=cd_cvm,
            demonstracao=dem,
            anos=anos_usados,
        )

        resultado[f"{dem}_LINHAS"] = len(base)
        resultado[f"{dem}_CONTAS"] = (
            int(base["CD_CONTA"].nunique())
            if not base.empty
            else 0
        )

    return resultado

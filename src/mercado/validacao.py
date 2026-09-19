from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.mercado.identidade import validar_invariantes_identidade
from src.mercado.ingestao import validar_precos_na_vigencia


@dataclass(frozen=True)
class Descontinuidade:
    instrumento_id: int
    data_anterior: object
    data_atual: object
    fechamento_anterior: float
    fechamento_atual: float
    retorno_log: float


def detectar_descontinuidades(
    con: duckdb.DuckDBPyConnection,
    *,
    limiar_abs_log: float = 0.35,
) -> list[Descontinuidade]:
    """
    Sinaliza movimentos extremos; não rejeita preços.

    O limiar padrão de 0,35 em log-retorno é apenas gate operacional
    do piloto e permanece configurável.
    """
    if limiar_abs_log <= 0:
        raise ValueError("limiar_abs_log deve ser positivo.")

    linhas = con.execute(
        """
        WITH ordenado AS (
            SELECT
                INSTRUMENTO_ID,
                DATA,
                FECHAMENTO,
                LAG(DATA) OVER (
                    PARTITION BY INSTRUMENTO_ID
                    ORDER BY DATA
                ) AS DATA_ANTERIOR,
                LAG(FECHAMENTO) OVER (
                    PARTITION BY INSTRUMENTO_ID
                    ORDER BY DATA
                ) AS FECHAMENTO_ANTERIOR
            FROM precos_diarios
            WHERE FECHAMENTO IS NOT NULL
        )
        SELECT
            INSTRUMENTO_ID,
            DATA_ANTERIOR,
            DATA,
            FECHAMENTO_ANTERIOR,
            FECHAMENTO
        FROM ordenado
        WHERE FECHAMENTO_ANTERIOR IS NOT NULL
          AND FECHAMENTO_ANTERIOR > 0
          AND FECHAMENTO > 0
        ORDER BY INSTRUMENTO_ID, DATA
        """
    ).fetchall()

    saida: list[Descontinuidade] = []

    for instrumento_id, data_ant, data_atual, preco_ant, preco_atual in linhas:
        retorno_log = math.log(float(preco_atual) / float(preco_ant))
        if abs(retorno_log) >= limiar_abs_log:
            saida.append(
                Descontinuidade(
                    instrumento_id=int(instrumento_id),
                    data_anterior=data_ant,
                    data_atual=data_atual,
                    fechamento_anterior=float(preco_ant),
                    fechamento_atual=float(preco_atual),
                    retorno_log=retorno_log,
                )
            )

    return saida


def validar_cd_cvm_no_catalogo_cvm(
    con_mercado: duckdb.DuckDBPyConnection,
    *,
    caminho_cvm: str | Path,
) -> list[str]:
    """
    Retorna CD_CVM presentes no Mercado e ausentes do catálogo CVM.

    Usa ATTACH somente leitura e faz DETACH ao final.
    """
    caminho = Path(caminho_cvm)

    if not caminho.is_file():
        raise FileNotFoundError(f"Banco CVM não encontrado: {caminho}")

    caminho_sql = str(caminho).replace("'", "''")
    alias = "cvm_readonly"

    try:
        con_mercado.execute(
            f"ATTACH '{caminho_sql}' AS {alias} (READ_ONLY)"
        )

        linhas = con_mercado.execute(
            f"""
            SELECT DISTINCT i.CD_CVM
            FROM instrumentos AS i
            LEFT JOIN {alias}.empresas AS e
              ON e.CD_CVM = i.CD_CVM
            WHERE e.CD_CVM IS NULL
            ORDER BY i.CD_CVM
            """
        ).fetchall()

        return [str(linha[0]) for linha in linhas]
    finally:
        try:
            con_mercado.execute(f"DETACH {alias}")
        except Exception:
            pass


def validar_gate_piloto(
    con: duckdb.DuckDBPyConnection,
    *,
    caminho_cvm: str | Path,
) -> dict[str, object]:
    falhas_identidade = validar_invariantes_identidade(con)
    precos_fora_vigencia = validar_precos_na_vigencia(con)
    cd_cvm_ausentes = validar_cd_cvm_no_catalogo_cvm(
        con,
        caminho_cvm=caminho_cvm,
    )

    return {
        "falhas_identidade": falhas_identidade,
        "precos_fora_vigencia": int(precos_fora_vigencia),
        "cd_cvm_ausentes": cd_cvm_ausentes,
        "aprovado": (
            not falhas_identidade
            and int(precos_fora_vigencia) == 0
            and not cd_cvm_ausentes
        ),
    }

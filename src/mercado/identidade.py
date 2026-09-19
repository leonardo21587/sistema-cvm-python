from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb


class InstrumentoNaoEncontrado(LookupError):
    """Nenhum instrumento e valido para bolsa+ticker+data."""


class IdentidadeAmbigua(RuntimeError):
    """Mais de um instrumento e valido para bolsa+ticker+data."""


@dataclass(frozen=True)
class FalhaInvariante:
    codigo: str
    quantidade: int


def normalizar_cd_cvm(valor: str | int) -> str:
    """
    Normaliza CD_CVM para texto com seis posicoes e zeros a esquerda.
    """
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]

    if not texto.isdigit():
        raise ValueError(f"CD_CVM invalido: {valor!r}")

    if len(texto) > 6:
        raise ValueError(f"CD_CVM excede 6 posicoes: {valor!r}")

    return texto.zfill(6)


def normalizar_bolsa(valor: str) -> str:
    bolsa = str(valor).strip().upper()
    if not bolsa:
        raise ValueError("BOLSA nao pode ser vazia.")
    if len(bolsa) > 8:
        raise ValueError("BOLSA excede 8 posicoes.")
    return bolsa


def normalizar_ticker(valor: str) -> str:
    ticker = str(valor).strip().upper()
    if not ticker:
        raise ValueError("TICKER nao pode ser vazio.")
    if len(ticker) > 12:
        raise ValueError("TICKER excede 12 posicoes.")
    return ticker


def resolver_instrumento(
    con: duckdb.DuckDBPyConnection,
    *,
    bolsa: str,
    ticker: str,
    data_referencia: date | str,
) -> int:
    """
    Resolve a identidade exclusivamente por (BOLSA, TICKER, DATA).

    A vigencia e semiaberta: [DT_INICIO, DT_FIM).
    O instrumento tambem precisa estar vigente na mesma data.
    """
    bolsa = normalizar_bolsa(bolsa)
    ticker = normalizar_ticker(ticker)

    linhas = con.execute(
        """
        SELECT DISTINCT th.INSTRUMENTO_ID
        FROM tickers_historico AS th
        JOIN instrumentos AS i
          ON i.INSTRUMENTO_ID = th.INSTRUMENTO_ID
        WHERE th.BOLSA = ?
          AND th.TICKER = ?
          AND th.DT_INICIO <= CAST(? AS DATE)
          AND (
                th.DT_FIM IS NULL
                OR CAST(? AS DATE) < th.DT_FIM
          )
          AND i.DT_INICIO <= CAST(? AS DATE)
          AND (
                i.DT_FIM IS NULL
                OR CAST(? AS DATE) < i.DT_FIM
          )
        ORDER BY th.INSTRUMENTO_ID
        """,
        [
            bolsa,
            ticker,
            data_referencia,
            data_referencia,
            data_referencia,
            data_referencia,
        ],
    ).fetchall()

    if not linhas:
        raise InstrumentoNaoEncontrado(
            f"Nenhum instrumento para {bolsa}:{ticker} em {data_referencia}."
        )

    if len(linhas) > 1:
        ids = [int(linha[0]) for linha in linhas]
        raise IdentidadeAmbigua(
            f"Identidade ambigua para {bolsa}:{ticker} em "
            f"{data_referencia}: {ids}"
        )

    return int(linhas[0][0])


def _contar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0])


def validar_invariantes_identidade(
    con: duckdb.DuckDBPyConnection,
) -> list[FalhaInvariante]:
    """
    Valida os dois invariantes temporais que pertencem a D.2.

    D.3 acrescentara verificacoes que dependem de precos e do catalogo CVM.
    """
    sobreposicao_mesmo_instrumento = _contar(
        con,
        """
        SELECT COUNT(*)
        FROM (
            SELECT 1
            FROM tickers_historico a
            JOIN tickers_historico b
              ON a.INSTRUMENTO_ID = b.INSTRUMENTO_ID
             AND a.BOLSA = b.BOLSA
             AND (
                    a.TICKER <> b.TICKER
                    OR a.DT_INICIO <> b.DT_INICIO
                 )
             AND a.DT_INICIO < COALESCE(b.DT_FIM, DATE '9999-12-31')
             AND b.DT_INICIO < COALESCE(a.DT_FIM, DATE '9999-12-31')
            WHERE
                a.TICKER < b.TICKER
                OR (
                    a.TICKER = b.TICKER
                    AND a.DT_INICIO < b.DT_INICIO
                )
        )
        """,
    )

    ticker_simultaneo_em_instrumentos_distintos = _contar(
        con,
        """
        SELECT COUNT(*)
        FROM (
            SELECT 1
            FROM tickers_historico a
            JOIN tickers_historico b
              ON a.BOLSA = b.BOLSA
             AND a.TICKER = b.TICKER
             AND a.INSTRUMENTO_ID < b.INSTRUMENTO_ID
             AND a.DT_INICIO < COALESCE(b.DT_FIM, DATE '9999-12-31')
             AND b.DT_INICIO < COALESCE(a.DT_FIM, DATE '9999-12-31')
        )
        """,
    )

    falhas = [
        FalhaInvariante(
            codigo="D2_TICKER_SOBREPOSTO_NO_MESMO_INSTRUMENTO",
            quantidade=sobreposicao_mesmo_instrumento,
        ),
        FalhaInvariante(
            codigo="D2_TICKER_SIMULTANEO_EM_INSTRUMENTOS_DISTINTOS",
            quantidade=ticker_simultaneo_em_instrumentos_distintos,
        ),
    ]

    return [falha for falha in falhas if falha.quantidade > 0]


def exigir_invariantes_identidade(
    con: duckdb.DuckDBPyConnection,
) -> None:
    falhas = validar_invariantes_identidade(con)
    if not falhas:
        return

    resumo = ", ".join(
        f"{falha.codigo}={falha.quantidade}"
        for falha in falhas
    )
    raise RuntimeError(f"Falha nos invariantes de identidade: {resumo}")

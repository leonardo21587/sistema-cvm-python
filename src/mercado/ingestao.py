from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import duckdb

from src.mercado.identidade import resolver_instrumento
from src.mercado.providers.b3_cotahist import CotacaoB3


@dataclass(frozen=True)
class PrecoDiario:
    instrumento_id: int
    data: object
    ticker_origem: str
    abertura: Decimal | None
    maxima: Decimal | None
    minima: Decimal | None
    preco_medio: Decimal | None
    fechamento: Decimal | None
    qtd_negocios: int | None
    qtd_titulos: int | None
    volume_financeiro: Decimal | None
    moeda: str
    fonte: str
    arquivo_fonte: str
    coletado_em: datetime


CAMPOS_COMPARACAO = (
    "ticker_origem",
    "abertura",
    "maxima",
    "minima",
    "preco_medio",
    "fechamento",
    "qtd_negocios",
    "qtd_titulos",
    "volume_financeiro",
    "moeda",
)


def _agora_utc_sem_tz() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalizar_moeda_cotahist(valor: str) -> str:
    texto = str(valor).strip().upper()

    if texto in {"R$", "BRL"}:
        return "BRL"

    raise ValueError(
        f"Moeda COTAHIST fora do escopo inicial: {valor!r}"
    )


def cotacao_para_preco(
    con: duckdb.DuckDBPyConnection,
    cotacao: CotacaoB3,
    *,
    bolsa: str = "B3",
    fonte: str = "B3_COTAHIST",
    arquivo_fonte: str,
    coletado_em: datetime | None = None,
) -> PrecoDiario:
    """
    Resolve identidade antes de transformar a cotação em linha oficial.

    Nenhum preço é persistido com ticker sem instrumento temporalmente
    resolvido.
    """
    instrumento_id = resolver_instrumento(
        con,
        bolsa=bolsa,
        ticker=cotacao.ticker,
        data_referencia=cotacao.data,
    )

    return PrecoDiario(
        instrumento_id=instrumento_id,
        data=cotacao.data,
        ticker_origem=cotacao.ticker.strip().upper(),
        abertura=cotacao.abertura,
        maxima=cotacao.maxima,
        minima=cotacao.minima,
        preco_medio=cotacao.preco_medio,
        fechamento=cotacao.fechamento,
        qtd_negocios=cotacao.qtd_negocios,
        qtd_titulos=cotacao.qtd_titulos,
        volume_financeiro=cotacao.volume_financeiro,
        moeda=normalizar_moeda_cotahist(cotacao.moeda_referencia),
        fonte=fonte,
        arquivo_fonte=arquivo_fonte,
        coletado_em=coletado_em or _agora_utc_sem_tz(),
    )


def _tupla_comparacao(preco: PrecoDiario) -> tuple:
    return tuple(getattr(preco, campo) for campo in CAMPOS_COMPARACAO)


def _preco_existente(
    con: duckdb.DuckDBPyConnection,
    instrumento_id: int,
    data: object,
) -> PrecoDiario | None:
    linha = con.execute(
        """
        SELECT
            INSTRUMENTO_ID,
            DATA,
            TICKER_ORIGEM,
            ABERTURA,
            MAXIMA,
            MINIMA,
            PRECO_MEDIO,
            FECHAMENTO,
            QTD_NEGOCIOS,
            QTD_TITULOS,
            VOLUME_FINANCEIRO,
            MOEDA,
            FONTE,
            ARQUIVO_FONTE,
            COLETADO_EM
        FROM precos_diarios
        WHERE INSTRUMENTO_ID = ?
          AND DATA = ?
        """,
        [instrumento_id, data],
    ).fetchone()

    if linha is None:
        return None

    return PrecoDiario(
        instrumento_id=int(linha[0]),
        data=linha[1],
        ticker_origem=linha[2],
        abertura=linha[3],
        maxima=linha[4],
        minima=linha[5],
        preco_medio=linha[6],
        fechamento=linha[7],
        qtd_negocios=linha[8],
        qtd_titulos=linha[9],
        volume_financeiro=linha[10],
        moeda=linha[11],
        fonte=linha[12],
        arquivo_fonte=linha[13],
        coletado_em=linha[14],
    )


def _inserir_preco(
    con: duckdb.DuckDBPyConnection,
    preco: PrecoDiario,
) -> None:
    con.execute(
        """
        INSERT INTO precos_diarios (
            INSTRUMENTO_ID,
            DATA,
            TICKER_ORIGEM,
            ABERTURA,
            MAXIMA,
            MINIMA,
            PRECO_MEDIO,
            FECHAMENTO,
            QTD_NEGOCIOS,
            QTD_TITULOS,
            VOLUME_FINANCEIRO,
            MOEDA,
            FONTE,
            ARQUIVO_FONTE,
            COLETADO_EM
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            preco.instrumento_id,
            preco.data,
            preco.ticker_origem,
            preco.abertura,
            preco.maxima,
            preco.minima,
            preco.preco_medio,
            preco.fechamento,
            preco.qtd_negocios,
            preco.qtd_titulos,
            preco.volume_financeiro,
            preco.moeda,
            preco.fonte,
            preco.arquivo_fonte,
            preco.coletado_em,
        ],
    )


def _registrar_substituicao(
    con: duckdb.DuckDBPyConnection,
    anterior: PrecoDiario,
    novo: PrecoDiario,
    *,
    motivo: str,
    substituido_em: datetime,
) -> None:
    con.execute(
        """
        INSERT INTO precos_substituicoes VALUES (
            ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?
        )
        """,
        [
            anterior.instrumento_id,
            anterior.data,
            anterior.ticker_origem,
            anterior.abertura,
            anterior.maxima,
            anterior.minima,
            anterior.preco_medio,
            anterior.fechamento,
            anterior.qtd_negocios,
            anterior.qtd_titulos,
            anterior.volume_financeiro,
            anterior.moeda,
            anterior.fonte,
            anterior.arquivo_fonte,
            novo.ticker_origem,
            novo.abertura,
            novo.maxima,
            novo.minima,
            novo.preco_medio,
            novo.fechamento,
            novo.qtd_negocios,
            novo.qtd_titulos,
            novo.volume_financeiro,
            novo.moeda,
            novo.fonte,
            novo.arquivo_fonte,
            substituido_em,
            motivo,
        ],
    )


def _atualizar_preco(
    con: duckdb.DuckDBPyConnection,
    preco: PrecoDiario,
) -> None:
    con.execute(
        """
        UPDATE precos_diarios
        SET
            TICKER_ORIGEM = ?,
            ABERTURA = ?,
            MAXIMA = ?,
            MINIMA = ?,
            PRECO_MEDIO = ?,
            FECHAMENTO = ?,
            QTD_NEGOCIOS = ?,
            QTD_TITULOS = ?,
            VOLUME_FINANCEIRO = ?,
            MOEDA = ?,
            FONTE = ?,
            ARQUIVO_FONTE = ?,
            COLETADO_EM = ?
        WHERE INSTRUMENTO_ID = ?
          AND DATA = ?
        """,
        [
            preco.ticker_origem,
            preco.abertura,
            preco.maxima,
            preco.minima,
            preco.preco_medio,
            preco.fechamento,
            preco.qtd_negocios,
            preco.qtd_titulos,
            preco.volume_financeiro,
            preco.moeda,
            preco.fonte,
            preco.arquivo_fonte,
            preco.coletado_em,
            preco.instrumento_id,
            preco.data,
        ],
    )


def persistir_preco(
    con: duckdb.DuckDBPyConnection,
    preco: PrecoDiario,
    *,
    motivo_substituicao: str = "Fonte reapresentou observação diferente",
) -> str:
    """
    Persiste uma observação de forma idempotente.

    Retorna:
      - INSERIDO: chave ainda não existia;
      - IGUAL: replay sem mudança material;
      - ATUALIZADO: valor divergente substituiu a linha após log.
    """
    anterior = _preco_existente(
        con,
        preco.instrumento_id,
        preco.data,
    )

    if anterior is None:
        _inserir_preco(con, preco)
        return "INSERIDO"

    if _tupla_comparacao(anterior) == _tupla_comparacao(preco):
        return "IGUAL"

    momento = _agora_utc_sem_tz()

    con.execute("BEGIN TRANSACTION")
    try:
        _registrar_substituicao(
            con,
            anterior,
            preco,
            motivo=motivo_substituicao,
            substituido_em=momento,
        )
        _atualizar_preco(con, preco)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return "ATUALIZADO"


def validar_precos_na_vigencia(
    con: duckdb.DuckDBPyConnection,
    *,
    bolsa: str = "B3",
) -> int:
    """
    Conta preços que não encontram o mesmo ticker na vigência do instrumento.

    Zero é o único valor aceitável para promoção da carga.
    """
    resultado = con.execute(
        """
        SELECT COUNT(*)
        FROM precos_diarios p
        JOIN instrumentos i
          ON i.INSTRUMENTO_ID = p.INSTRUMENTO_ID
        LEFT JOIN tickers_historico th
          ON th.INSTRUMENTO_ID = p.INSTRUMENTO_ID
         AND th.BOLSA = ?
         AND th.TICKER = p.TICKER_ORIGEM
         AND th.DT_INICIO <= p.DATA
         AND (th.DT_FIM IS NULL OR p.DATA < th.DT_FIM)
        WHERE
            NOT (
                i.DT_INICIO <= p.DATA
                AND (i.DT_FIM IS NULL OR p.DATA < i.DT_FIM)
            )
            OR th.INSTRUMENTO_ID IS NULL
        """,
        [bolsa],
    ).fetchone()[0]

    return int(resultado)

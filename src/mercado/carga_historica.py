from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from src.mercado.catalogo import tickers_catalogados
from src.mercado.identidade import InstrumentoNaoEncontrado
from src.mercado.ingestao import cotacao_para_preco, persistir_preco
from src.mercado.providers.b3_cotahist import iterar_cotacoes


TIPO_MERCADO_VISTA = "010"


@dataclass
class ResultadoCargaArquivo:
    ano: int
    arquivo: str
    linhas_cotacao: int = 0
    linhas_fora_escopo: int = 0
    linhas_elegiveis: int = 0
    linhas_mapeadas: int = 0
    linhas_sem_instrumento: int = 0
    inseridos: int = 0
    iguais: int = 0
    atualizados: int = 0
    por_ticker: dict[str, int] = field(default_factory=dict)


def carregar_cotahist_catalogado(
    con: duckdb.DuckDBPyConnection,
    caminho: str | Path,
    *,
    ano: int,
    bolsa: str = "B3",
    fonte: str = "B3_COTAHIST",
) -> ResultadoCargaArquivo:
    """
    Carrega um COTAHIST anual apenas para tickers presentes no catálogo.

    O filtro de escopo da D.4 continua restrito ao mercado à vista (010)
    e aos instrumentos previamente auditados no catálogo versionado.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(caminho)

    tickers = tickers_catalogados()
    resultado = ResultadoCargaArquivo(
        ano=int(ano),
        arquivo=caminho.name,
        por_ticker={ticker: 0 for ticker in tickers},
    )

    for cotacao in iterar_cotacoes(caminho):
        resultado.linhas_cotacao += 1

        if cotacao.data.year != int(ano):
            raise RuntimeError(
                f"{caminho.name}: registro de {cotacao.data} fora do ano {ano}."
            )

        if (
            cotacao.tipo_mercado != TIPO_MERCADO_VISTA
            or cotacao.ticker not in tickers
        ):
            resultado.linhas_fora_escopo += 1
            continue

        resultado.linhas_elegiveis += 1

        try:
            preco = cotacao_para_preco(
                con,
                cotacao,
                bolsa=bolsa,
                fonte=fonte,
                arquivo_fonte=caminho.name,
            )
        except InstrumentoNaoEncontrado:
            resultado.linhas_sem_instrumento += 1
            continue

        resultado.linhas_mapeadas += 1
        resultado.por_ticker[cotacao.ticker] += 1

        status = persistir_preco(con, preco)

        if status == "INSERIDO":
            resultado.inseridos += 1
        elif status == "IGUAL":
            resultado.iguais += 1
        elif status == "ATUALIZADO":
            resultado.atualizados += 1
        else:
            raise RuntimeError(
                f"Status de persistência inesperado: {status!r}"
            )

    return resultado

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.mercado.classificacao import inferir_tipo_classe
from src.mercado.providers.b3_cotahist import iterar_cotacoes
from src.mercado.providers.cvm_fca import FcaValorMobiliario, ticker_formato_elegivel


@dataclass(frozen=True)
class ResumoTickerAno:
    ticker: str
    tipo_ativo: str
    classe: str
    primeira_data: date
    ultima_data: date
    pregoes: int
    isins: tuple[str, ...]
    especificacoes: tuple[str, ...]
    datas_por_isin: dict[str, tuple[date, date, int]]


@dataclass(frozen=True)
class VinculoFca:
    ticker: str
    cd_cvm: str | None
    cnpj: str | None
    status: str
    anos_fca: tuple[int, ...]
    quantidade_registros: int


def resumir_cotahist_ano(
    caminho: str | Path,
    *,
    ano: int,
    tipo_mercado: str = "010",
) -> dict[str, ResumoTickerAno]:
    """
    Resume todos os códigos que parecem ações/Units no COTAHIST do ano.

    O filtro final de escopo é dado pela especificação B3 + regras de
    classificação, não pelo simples sufixo do ticker.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(caminho)

    bruto: dict[str, dict] = defaultdict(
        lambda: {
            "datas": set(),
            "isins": defaultdict(set),
            "especificacoes": set(),
        }
    )

    for cotacao in iterar_cotacoes(caminho):
        if cotacao.data.year != int(ano):
            raise RuntimeError(
                f"{caminho.name}: registro {cotacao.data} fora de {ano}."
            )

        if cotacao.tipo_mercado != tipo_mercado:
            continue

        ticker = cotacao.ticker.strip().upper()
        if not ticker_formato_elegivel(ticker):
            continue

        item = bruto[ticker]
        item["datas"].add(cotacao.data)

        if cotacao.isin:
            item["isins"][cotacao.isin.strip().upper()].add(cotacao.data)

        if cotacao.especificacao:
            item["especificacoes"].add(cotacao.especificacao.strip().upper())

    saida: dict[str, ResumoTickerAno] = {}

    for ticker, item in bruto.items():
        especificacoes = tuple(sorted(item["especificacoes"]))
        tipo, classe = inferir_tipo_classe(
            ticker=ticker,
            especificacoes_cotahist="|".join(especificacoes),
        )

        # Bônus, direitos, recibos, FII/ETF etc. não entram no escopo inicial.
        if tipo is None or classe is None:
            continue

        datas = sorted(item["datas"])
        if not datas:
            continue

        datas_por_isin = {}
        for isin, datas_isin in item["isins"].items():
            ordenadas = sorted(datas_isin)
            datas_por_isin[isin] = (
                ordenadas[0],
                ordenadas[-1],
                len(set(ordenadas)),
            )

        saida[ticker] = ResumoTickerAno(
            ticker=ticker,
            tipo_ativo=tipo,
            classe=classe,
            primeira_data=datas[0],
            ultima_data=datas[-1],
            pregoes=len(set(datas)),
            isins=tuple(sorted(item["isins"])),
            especificacoes=especificacoes,
            datas_por_isin=datas_por_isin,
        )

    return saida


def indexar_fca_por_ticker(
    registros_por_ano: dict[int, list[FcaValorMobiliario]],
) -> dict[str, list[tuple[int, FcaValorMobiliario]]]:
    indice: dict[str, list[tuple[int, FcaValorMobiliario]]] = defaultdict(list)

    for ano, registros in registros_por_ano.items():
        for registro in registros:
            ticker = registro.codigo_negociacao.strip().upper()
            if ticker:
                indice[ticker].append((int(ano), registro))

    return indice


def resolver_vinculo_fca(
    ticker: str,
    indice_fca: dict[str, list[tuple[int, FcaValorMobiliario]]],
) -> VinculoFca:
    """
    Resolve companhia do ticker usando múltiplas fotografias anuais do FCA.

    Zero CD_CVM -> SEM_FCA.
    Mais de um CD_CVM -> AMBIGUO_CD_CVM.
    Um CD_CVM e mais de um CNPJ -> AMBIGUO_CNPJ.
    Caso contrário -> RESOLVIDO.
    """
    ticker = str(ticker).strip().upper()
    itens = indice_fca.get(ticker, [])

    if not itens:
        return VinculoFca(
            ticker=ticker,
            cd_cvm=None,
            cnpj=None,
            status="SEM_FCA",
            anos_fca=(),
            quantidade_registros=0,
        )

    codigos = {
        registro.cd_cvm
        for _, registro in itens
        if registro.cd_cvm
    }
    cnpjs = {
        registro.cnpj
        for _, registro in itens
        if registro.cnpj
    }
    anos = tuple(sorted({ano for ano, _ in itens}))

    if len(codigos) == 0:
        status = "CD_CVM_NAO_RESOLVIDO"
        cd_cvm = None
    elif len(codigos) > 1:
        status = "AMBIGUO_CD_CVM"
        cd_cvm = None
    else:
        status = "RESOLVIDO"
        cd_cvm = next(iter(codigos))

    if status == "RESOLVIDO" and len(cnpjs) > 1:
        status = "AMBIGUO_CNPJ"

    cnpj = next(iter(cnpjs)) if len(cnpjs) == 1 else None

    return VinculoFca(
        ticker=ticker,
        cd_cvm=cd_cvm,
        cnpj=cnpj,
        status=status,
        anos_fca=anos,
        quantidade_registros=len(itens),
    )


def intervalos_ticker_sobrepostos(
    resumos: list[ResumoTickerAno],
) -> list[tuple[str, str]]:
    """
    Retorna pares de tickers cujas janelas observadas no ano se sobrepõem.
    """
    conflitos = []

    ordenados = sorted(
        resumos,
        key=lambda item: (item.primeira_data, item.ticker),
    )

    for indice, atual in enumerate(ordenados):
        for proximo in ordenados[indice + 1:]:
            if proximo.primeira_data > atual.ultima_data:
                break
            if (
                atual.primeira_data <= proximo.ultima_data
                and proximo.primeira_data <= atual.ultima_data
            ):
                conflitos.append((atual.ticker, proximo.ticker))

    return conflitos

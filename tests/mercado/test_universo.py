from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.providers.cvm_fca import FcaValorMobiliario  # noqa: E402
from src.mercado.universo import (  # noqa: E402
    ResumoTickerAno,
    indexar_fca_por_ticker,
    intervalos_ticker_sobrepostos,
    resolver_vinculo_fca,
)


def _fca(ticker, cd_cvm, cnpj):
    return FcaValorMobiliario(
        cd_cvm=cd_cvm,
        cnpj=cnpj,
        data_referencia=date(2025, 1, 1),
        versao=1,
        id_documento="1",
        nome_empresarial="TESTE",
        valor_mobiliario="Ações Ordinárias",
        sigla_classe_preferencial="",
        classe_preferencial="",
        codigo_negociacao=ticker,
        composicao_bdr_unit="",
        mercado="Bolsa",
        sigla_entidade_administradora="B3",
        entidade_administradora="B3",
        data_inicio_negociacao=None,
        data_fim_negociacao=None,
        segmento="",
        data_inicio_listagem=None,
        data_fim_listagem=None,
    )


def _resumo(ticker, inicio, fim):
    return ResumoTickerAno(
        ticker=ticker,
        tipo_ativo="ACAO",
        classe="ON",
        primeira_data=inicio,
        ultima_data=fim,
        pregoes=1,
        isins=("BRTESTACNOR0",),
        especificacoes=("ON",),
        datas_por_isin={},
    )


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.4 — UNIVERSO AMPLIADO")
    print("=" * 72)

    indice = indexar_fca_por_ticker({
        2025: [_fca("ELET3", "002437", "00001180000126")],
        2026: [_fca("AXIA3", "002437", "00001180000126")],
    })

    elet = resolver_vinculo_fca("ELET3", indice)
    axia = resolver_vinculo_fca("AXIA3", indice)
    vazio = resolver_vinculo_fca("XXXX3", indice)

    assert elet.status == "RESOLVIDO"
    assert axia.status == "RESOLVIDO"
    assert elet.cd_cvm == axia.cd_cvm == "002437"
    assert vazio.status == "SEM_FCA"

    nao_sobrepoe = intervalos_ticker_sobrepostos([
        _resumo("ELET3", date(2025, 1, 2), date(2025, 11, 7)),
        _resumo("AXIA3", date(2025, 11, 10), date(2025, 12, 30)),
    ])
    assert nao_sobrepoe == []

    sobrepoe = intervalos_ticker_sobrepostos([
        _resumo("AAA3", date(2025, 1, 2), date(2025, 6, 30)),
        _resumo("BBB3", date(2025, 6, 1), date(2025, 12, 30)),
    ])
    assert sobrepoe == [("AAA3", "BBB3")]

    print("RESULTADO: APROVADO")
    print("FCA multiano: aprovado")
    print("ticker sem FCA: explicitamente sinalizado")
    print("continuidade sem sobreposição: aprovada")
    print("sobreposição de tickers: detectada")


if __name__ == "__main__":
    main()

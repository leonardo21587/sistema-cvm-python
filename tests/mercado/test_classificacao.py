from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.classificacao import (  # noqa: E402
    inferir_tipo_classe,
    instrumento_fca_no_escopo_inicial,
)


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.4 — CLASSIFICAÇÃO DE INSTRUMENTOS")
    print("=" * 72)

    assert inferir_tipo_classe(
        ticker="PETR3",
        especificacoes_cotahist="ON      N2",
    ) == ("ACAO", "ON")

    assert inferir_tipo_classe(
        ticker="PETR4",
        especificacoes_cotahist="PN      N2",
    ) == ("ACAO", "PN")

    assert inferir_tipo_classe(
        ticker="TEST5",
        especificacoes_cotahist="PNA",
    ) == ("ACAO", "PNA")

    assert inferir_tipo_classe(
        ticker="TEST6",
        sigla_classe_preferencial="PNB",
        especificacoes_cotahist="PNB",
    ) == ("ACAO", "PNB")

    assert inferir_tipo_classe(
        ticker="TAEE11",
        valor_mobiliario="Units",
        composicao_unit="1 ON + 2 PN",
        especificacoes_cotahist="UNT N2",
    ) == ("UNIT", "UNIT")

    assert inferir_tipo_classe(
        ticker="RAIZ4",
        valor_mobiliario="Ações Preferenciais",
    ) == ("ACAO", "PN")

    assert instrumento_fca_no_escopo_inicial(
        ticker="TAEE11",
        valor_mobiliario="Units",
        composicao_unit="1 ON + 2 PN",
        especificacoes_cotahist="UNT N2",
    )

    for ticker, valor, especificacao in [
        ("CALI11", "Bônus de Subscrição", "BNS ORD"),
        ("AZEV11", "Bônus de Subscrição", "BNS"),
        ("IFCM11", "Bônus de Subscrição", "DIR NM"),
    ]:
        assert not instrumento_fca_no_escopo_inicial(
            ticker=ticker,
            valor_mobiliario=valor,
            especificacoes_cotahist=especificacao,
        )

    # Não inferimos classe A/B/C/D apenas pelo número final do ticker.
    assert inferir_tipo_classe(
        ticker="TEST5",
    ) == (None, None)

    print("RESULTADO: APROVADO")
    print("ON: aprovada")
    print("PN genérica via COTAHIST: aprovada")
    print("PNA/PNB por fonte explícita: aprovadas")
    print("UNIT: aprovada")
    print("PN genérica via Valor_Mobiliario: aprovada")
    print("bônus/direitos com final 11: fora do escopo")
    print("inferência por sufixo sem evidência: bloqueada")


if __name__ == "__main__":
    main()

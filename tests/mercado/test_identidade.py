from __future__ import annotations

import sys
from pathlib import Path

import duckdb


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.identidade import (  # noqa: E402
    IdentidadeAmbigua,
    InstrumentoNaoEncontrado,
    exigir_invariantes_identidade,
    normalizar_cd_cvm,
    resolver_instrumento,
    validar_invariantes_identidade,
)
from src.mercado.schema import criar_schema_identidade  # noqa: E402


def inserir_instrumento(
    con,
    instrumento_id,
    cd_cvm,
    tipo_ativo,
    classe,
    dt_inicio,
    dt_fim,
    status,
    fonte="FIXTURE",
):
    con.execute(
        """
        INSERT INTO instrumentos VALUES (?, ?, ?, ?, 'BRL', ?, ?, ?, ?)
        """,
        [
            instrumento_id,
            cd_cvm,
            tipo_ativo,
            classe,
            dt_inicio,
            dt_fim,
            status,
            fonte,
        ],
    )


def inserir_identificador(
    con,
    instrumento_id,
    tipo_identificador,
    valor,
    dt_inicio,
    dt_fim,
    fonte="FIXTURE",
):
    con.execute(
        """
        INSERT INTO instrumentos_identificadores
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            instrumento_id,
            tipo_identificador,
            valor,
            dt_inicio,
            dt_fim,
            fonte,
        ],
    )


def inserir_ticker(
    con,
    instrumento_id,
    ticker,
    dt_inicio,
    dt_fim,
    status,
    bolsa="B3",
    fonte="FIXTURE",
):
    con.execute(
        """
        INSERT INTO tickers_historico
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            instrumento_id,
            bolsa,
            ticker,
            dt_inicio,
            dt_fim,
            status,
            fonte,
        ],
    )


def montar_fixtures(con):
    # Petrobras: uma companhia, ON e PN como instrumentos paralelos.
    inserir_instrumento(
        con, 1001, "009512", "ACAO", "ON",
        "2010-01-01", None, "ATIVO"
    )
    inserir_instrumento(
        con, 1002, "009512", "ACAO", "PN",
        "2010-01-01", None, "ATIVO"
    )
    inserir_identificador(
        con, 1001, "ISIN", "BRPETRACNOR9", "2010-01-01", None
    )
    inserir_identificador(
        con, 1002, "ISIN", "BRPETRACNPR6", "2010-01-01", None
    )
    inserir_ticker(con, 1001, "PETR3", "2010-01-01", None, "VIGENTE")
    inserir_ticker(con, 1002, "PETR4", "2010-01-01", None, "VIGENTE")

    # TAESA: Unit e instrumento independente.
    inserir_instrumento(
        con, 2001, "020257", "UNIT", "UNIT",
        "2010-01-01", None, "ATIVO"
    )
    inserir_ticker(con, 2001, "TAEE11", "2010-01-01", None, "VIGENTE")

    # Eletrobras/Axia: mudanca de ticker em intervalo semiaberto.
    inserir_instrumento(
        con, 3001, "002437", "ACAO", "ON",
        "2010-01-01", None, "ATIVO"
    )
    inserir_ticker(
        con, 3001, "ELET3",
        "2010-01-01", "2025-11-10", "ENCERRADO"
    )
    inserir_ticker(
        con, 3001, "AXIA3",
        "2025-11-10", None, "VIGENTE"
    )

    # Magazine Luiza: grupamento nao cria novo instrumento/ticker.
    inserir_instrumento(
        con, 4001, "022470", "ACAO", "ON",
        "2010-01-01", None, "ATIVO"
    )
    inserir_ticker(con, 4001, "MGLU3", "2010-01-01", None, "VIGENTE")

    # Natura: NATU3 antigo, NTCO3 e NATU3 atual ficam separados na D.2.
    # Continuidade/sucessao societaria sera tratada somente na Fase F.
    inserir_instrumento(
        con, 5001, "019550", "ACAO", "ON",
        "2010-01-01", "2019-12-18", "ENCERRADO"
    )
    inserir_ticker(
        con, 5001, "NATU3",
        "2010-01-01", "2019-12-18", "ENCERRADO"
    )

    inserir_instrumento(
        con, 5002, "024783", "ACAO", "ON",
        "2019-12-18", "2025-07-02", "ENCERRADO"
    )
    inserir_ticker(
        con, 5002, "NTCO3",
        "2019-12-18", "2025-07-02", "ENCERRADO"
    )

    inserir_instrumento(
        con, 5003, "019550", "ACAO", "ON",
        "2025-07-02", None, "ATIVO"
    )
    inserir_ticker(
        con, 5003, "NATU3",
        "2025-07-02", None, "VIGENTE"
    )


def teste_normalizacao():
    assert normalizar_cd_cvm("9512") == "009512"
    assert normalizar_cd_cvm(2437) == "002437"


def teste_fixtures_reais(con):
    assert resolver_instrumento(
        con, bolsa="B3", ticker="PETR3", data_referencia="2026-01-02"
    ) == 1001
    assert resolver_instrumento(
        con, bolsa="B3", ticker="PETR4", data_referencia="2026-01-02"
    ) == 1002

    isins = con.execute(
        """
        SELECT VALOR
        FROM instrumentos_identificadores
        WHERE INSTRUMENTO_ID IN (1001, 1002)
        ORDER BY VALOR
        """
    ).fetchall()
    assert isins == [("BRPETRACNOR9",), ("BRPETRACNPR6",)]

    assert resolver_instrumento(
        con, bolsa="B3", ticker="TAEE11", data_referencia="2026-01-02"
    ) == 2001

    assert resolver_instrumento(
        con, bolsa="B3", ticker="ELET3", data_referencia="2025-11-07"
    ) == 3001
    assert resolver_instrumento(
        con, bolsa="B3", ticker="AXIA3", data_referencia="2025-11-10"
    ) == 3001

    try:
        resolver_instrumento(
            con, bolsa="B3", ticker="ELET3", data_referencia="2025-11-10"
        )
    except InstrumentoNaoEncontrado:
        pass
    else:
        raise AssertionError("ELET3 nao deveria resolver em 10/11/2025.")

    # 27/05/2024 e a data de inicio da negociacao grupada 10:1.
    assert resolver_instrumento(
        con, bolsa="B3", ticker="MGLU3", data_referencia="2024-05-24"
    ) == 4001
    assert resolver_instrumento(
        con, bolsa="B3", ticker="MGLU3", data_referencia="2024-05-27"
    ) == 4001

    assert resolver_instrumento(
        con, bolsa="B3", ticker="NATU3", data_referencia="2019-12-17"
    ) == 5001
    assert resolver_instrumento(
        con, bolsa="B3", ticker="NTCO3", data_referencia="2019-12-18"
    ) == 5002
    assert resolver_instrumento(
        con, bolsa="B3", ticker="NATU3", data_referencia="2025-07-02"
    ) == 5003

    try:
        resolver_instrumento(
            con, bolsa="B3", ticker="NATU3", data_referencia="2020-01-02"
        )
    except InstrumentoNaoEncontrado:
        pass
    else:
        raise AssertionError("NATU3 nao deveria resolver durante o intervalo NTCO3.")

    exigir_invariantes_identidade(con)


def teste_ambiguidade_bloqueada():
    con = duckdb.connect(":memory:")
    try:
        criar_schema_identidade(con)

        inserir_instrumento(
            con, 9001, "000001", "ACAO", "ON",
            "2020-01-01", None, "ATIVO"
        )
        inserir_instrumento(
            con, 9002, "000002", "ACAO", "ON",
            "2020-01-01", None, "ATIVO"
        )
        inserir_ticker(con, 9001, "TEST3", "2020-01-01", None, "VIGENTE")
        inserir_ticker(con, 9002, "TEST3", "2021-01-01", None, "VIGENTE")

        falhas = validar_invariantes_identidade(con)
        assert any(
            f.codigo == "D2_TICKER_SIMULTANEO_EM_INSTRUMENTOS_DISTINTOS"
            for f in falhas
        )

        try:
            resolver_instrumento(
                con, bolsa="B3", ticker="TEST3", data_referencia="2022-01-03"
            )
        except IdentidadeAmbigua:
            pass
        else:
            raise AssertionError("Ticker ambiguo deveria bloquear a resolucao.")
    finally:
        con.close()


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.2 — IDENTIDADE DE MERCADO")
    print("=" * 72)

    teste_normalizacao()

    con = duckdb.connect(":memory:")
    try:
        criar_schema_identidade(con)
        montar_fixtures(con)
        teste_fixtures_reais(con)
    finally:
        con.close()

    teste_ambiguidade_bloqueada()

    print("RESULTADO: APROVADO")
    print(
        "Fixtures: PETR3/PETR4, TAEE11, ELET3->AXIA3, "
        "MGLU3, NATU3/NTCO3/NATU3"
    )
    print("Invariantes temporais D.2: verdes")


if __name__ == "__main__":
    main()

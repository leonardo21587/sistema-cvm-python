from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.ingestao import (  # noqa: E402
    cotacao_para_preco,
    persistir_preco,
    validar_precos_na_vigencia,
)
from src.mercado.providers.b3_cotahist import CotacaoB3  # noqa: E402
from src.mercado.schema import conectar_mercado, criar_schema_mercado  # noqa: E402


def preparar_banco():
    con = conectar_mercado(":memory:")
    criar_schema_mercado(con)

    con.execute(
        """
        INSERT INTO instrumentos VALUES
        (1001, '004170', 'ACAO', 'ON', 'BRL',
         DATE '2010-01-01', NULL, 'ATIVO', 'FIXTURE')
        """
    )
    con.execute(
        """
        INSERT INTO tickers_historico VALUES
        (1001, 'B3', 'VALE3', DATE '2010-01-01',
         NULL, 'VIGENTE', 'FIXTURE')
        """
    )

    return con


def cotacao_vale(*, fechamento=Decimal("61.01"), volume=Decimal("600000123.45")):
    return CotacaoB3(
        data=date(2025, 9, 19),
        cod_bdi="02",
        ticker="VALE3",
        tipo_mercado="010",
        nome_resumido="VALE",
        especificacao="ON",
        prazo_termo=None,
        moeda_referencia="R$",
        abertura=Decimal("60.12"),
        maxima=Decimal("61.50"),
        minima=Decimal("59.88"),
        preco_medio=Decimal("60.66"),
        fechamento=fechamento,
        melhor_oferta_compra=Decimal("61.00"),
        melhor_oferta_venda=Decimal("61.02"),
        qtd_negocios=1234,
        qtd_titulos=9876543,
        volume_financeiro=volume,
        preco_exercicio=Decimal("0.00"),
        indicador_correcao="0",
        data_vencimento=None,
        fator_cotacao=1,
        preco_exercicio_pontos=Decimal("0.000000"),
        isin="BRVALEACNOR0",
        numero_distribuicao=123,
    )


def teste_insercao_e_idempotencia():
    con = preparar_banco()
    try:
        instante = datetime(2026, 9, 19, 7, 0, 0)

        preco = cotacao_para_preco(
            con,
            cotacao_vale(),
            arquivo_fonte="COTAHIST.2025.TXT",
            coletado_em=instante,
        )

        assert persistir_preco(con, preco) == "INSERIDO"
        assert persistir_preco(con, preco) == "IGUAL"

        linha = con.execute(
            """
            SELECT
                INSTRUMENTO_ID,
                DATA,
                TICKER_ORIGEM,
                FECHAMENTO,
                VOLUME_FINANCEIRO,
                MOEDA,
                FONTE,
                ARQUIVO_FONTE
            FROM precos_diarios
            """
        ).fetchone()

        assert linha == (
            1001,
            date(2025, 9, 19),
            "VALE3",
            Decimal("61.010000"),
            Decimal("600000123.45"),
            "BRL",
            "B3_COTAHIST",
            "COTAHIST.2025.TXT",
        )

        substituicoes = con.execute(
            "SELECT COUNT(*) FROM precos_substituicoes"
        ).fetchone()[0]
        assert substituicoes == 0

        assert validar_precos_na_vigencia(con) == 0
    finally:
        con.close()


def teste_substituicao_auditada():
    con = preparar_banco()
    try:
        preco_original = cotacao_para_preco(
            con,
            cotacao_vale(),
            arquivo_fonte="COTAHIST.2025.TXT",
            coletado_em=datetime(2026, 9, 19, 7, 0, 0),
        )
        assert persistir_preco(con, preco_original) == "INSERIDO"

        preco_revisado = cotacao_para_preco(
            con,
            cotacao_vale(
                fechamento=Decimal("61.11"),
                volume=Decimal("600100123.45"),
            ),
            arquivo_fonte="COTAHIST.2025.REV1.TXT",
            coletado_em=datetime(2026, 9, 20, 7, 0, 0),
        )

        assert persistir_preco(
            con,
            preco_revisado,
            motivo_substituicao="Fixture de revisão",
        ) == "ATUALIZADO"

        atual = con.execute(
            """
            SELECT FECHAMENTO, VOLUME_FINANCEIRO, ARQUIVO_FONTE
            FROM precos_diarios
            """
        ).fetchone()
        assert atual == (
            Decimal("61.110000"),
            Decimal("600100123.45"),
            "COTAHIST.2025.REV1.TXT",
        )

        log = con.execute(
            """
            SELECT
                FECHAMENTO_ANTERIOR,
                FECHAMENTO_NOVO,
                ARQUIVO_FONTE_ANTERIOR,
                ARQUIVO_FONTE_NOVO,
                MOTIVO
            FROM precos_substituicoes
            """
        ).fetchone()

        assert log == (
            Decimal("61.010000"),
            Decimal("61.110000"),
            "COTAHIST.2025.TXT",
            "COTAHIST.2025.REV1.TXT",
            "Fixture de revisão",
        )
    finally:
        con.close()


def teste_preco_fora_da_vigencia_detectado():
    con = preparar_banco()
    try:
        con.execute(
            """
            UPDATE tickers_historico
            SET DT_FIM = DATE '2025-09-19',
                STATUS = 'ENCERRADO'
            WHERE INSTRUMENTO_ID = 1001
            """
        )

        con.execute(
            """
            INSERT INTO precos_diarios VALUES (
                1001,
                DATE '2025-09-19',
                'VALE3',
                60.12,
                61.50,
                59.88,
                60.66,
                61.01,
                1234,
                9876543,
                600000123.45,
                'BRL',
                'FIXTURE',
                'fixture.txt',
                TIMESTAMP '2026-09-19 07:00:00'
            )
            """
        )

        assert validar_precos_na_vigencia(con) == 1
    finally:
        con.close()


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.3 — PREÇOS E IDEMPOTÊNCIA")
    print("=" * 72)

    teste_insercao_e_idempotencia()
    teste_substituicao_auditada()
    teste_preco_fora_da_vigencia_detectado()

    print("RESULTADO: APROVADO")
    print("precos_diarios: aprovado")
    print("replay idempotente: aprovado")
    print("substituição auditada: aprovado")
    print("vigência preço/ticker: aprovada")


if __name__ == "__main__":
    main()

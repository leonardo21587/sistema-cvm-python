from __future__ import annotations

from pathlib import Path
from typing import Union

import duckdb


ROOT_DIR = Path(__file__).resolve().parents[2]
MERCADO_DUCKDB = ROOT_DIR / "data" / "processed" / "mercado.duckdb"

DatabaseTarget = Union[str, Path]


DDL_INSTRUMENTOS = """
CREATE TABLE IF NOT EXISTS instrumentos (
    INSTRUMENTO_ID BIGINT PRIMARY KEY,
    CD_CVM VARCHAR NOT NULL,
    TIPO_ATIVO VARCHAR NOT NULL,
    CLASSE VARCHAR NOT NULL,
    MOEDA VARCHAR NOT NULL DEFAULT 'BRL',
    DT_INICIO DATE NOT NULL,
    DT_FIM DATE,
    STATUS VARCHAR NOT NULL,
    FONTE VARCHAR NOT NULL,

    CHECK (regexp_full_match(CD_CVM, '[0-9]{6}')),
    CHECK (TIPO_ATIVO IN ('ACAO', 'UNIT')),
    CHECK (CLASSE IN ('ON', 'PN', 'PNA', 'PNB', 'PNC', 'PND', 'UNIT')),
    CHECK (
        (TIPO_ATIVO = 'UNIT' AND CLASSE = 'UNIT')
        OR
        (TIPO_ATIVO = 'ACAO' AND CLASSE IN ('ON', 'PN', 'PNA', 'PNB', 'PNC', 'PND'))
    ),
    CHECK (regexp_full_match(MOEDA, '[A-Z]{3}')),
    CHECK (DT_FIM IS NULL OR DT_FIM > DT_INICIO),
    CHECK (STATUS IN ('ATIVO', 'ENCERRADO')),
    CHECK (
        (STATUS = 'ATIVO' AND DT_FIM IS NULL)
        OR
        (STATUS = 'ENCERRADO' AND DT_FIM IS NOT NULL)
    )
)
"""

DDL_IDENTIFICADORES = """
CREATE TABLE IF NOT EXISTS instrumentos_identificadores (
    INSTRUMENTO_ID BIGINT NOT NULL,
    TIPO_IDENTIFICADOR VARCHAR NOT NULL,
    VALOR VARCHAR NOT NULL,
    DT_INICIO DATE NOT NULL,
    DT_FIM DATE,
    FONTE VARCHAR NOT NULL,

    PRIMARY KEY (
        INSTRUMENTO_ID,
        TIPO_IDENTIFICADOR,
        VALOR,
        DT_INICIO
    ),
    FOREIGN KEY (INSTRUMENTO_ID)
        REFERENCES instrumentos(INSTRUMENTO_ID),
    CHECK (TIPO_IDENTIFICADOR IN ('ISIN')),
    CHECK (length(VALOR) BETWEEN 1 AND 32),
    CHECK (DT_FIM IS NULL OR DT_FIM > DT_INICIO)
)
"""

DDL_TICKERS = """
CREATE TABLE IF NOT EXISTS tickers_historico (
    INSTRUMENTO_ID BIGINT NOT NULL,
    BOLSA VARCHAR NOT NULL,
    TICKER VARCHAR NOT NULL,
    DT_INICIO DATE NOT NULL,
    DT_FIM DATE,
    STATUS VARCHAR NOT NULL,
    FONTE VARCHAR NOT NULL,

    PRIMARY KEY (
        INSTRUMENTO_ID,
        BOLSA,
        TICKER,
        DT_INICIO
    ),
    FOREIGN KEY (INSTRUMENTO_ID)
        REFERENCES instrumentos(INSTRUMENTO_ID),
    CHECK (length(BOLSA) BETWEEN 1 AND 8),
    CHECK (length(TICKER) BETWEEN 1 AND 12),
    CHECK (DT_FIM IS NULL OR DT_FIM > DT_INICIO),
    CHECK (STATUS IN ('VIGENTE', 'ENCERRADO')),
    CHECK (
        (STATUS = 'VIGENTE' AND DT_FIM IS NULL)
        OR
        (STATUS = 'ENCERRADO' AND DT_FIM IS NOT NULL)
    )
)
"""

DDL_PRECOS_DIARIOS = """
CREATE TABLE IF NOT EXISTS precos_diarios (
    INSTRUMENTO_ID BIGINT NOT NULL,
    DATA DATE NOT NULL,
    TICKER_ORIGEM VARCHAR NOT NULL,
    ABERTURA DECIMAL(20,6),
    MAXIMA DECIMAL(20,6),
    MINIMA DECIMAL(20,6),
    PRECO_MEDIO DECIMAL(20,6),
    FECHAMENTO DECIMAL(20,6),
    QTD_NEGOCIOS BIGINT,
    QTD_TITULOS BIGINT,
    VOLUME_FINANCEIRO DECIMAL(24,2),
    MOEDA VARCHAR NOT NULL,
    FONTE VARCHAR NOT NULL,
    ARQUIVO_FONTE VARCHAR NOT NULL,
    COLETADO_EM TIMESTAMP NOT NULL,

    PRIMARY KEY (INSTRUMENTO_ID, DATA),
    FOREIGN KEY (INSTRUMENTO_ID)
        REFERENCES instrumentos(INSTRUMENTO_ID),
    CHECK (length(TICKER_ORIGEM) BETWEEN 1 AND 12),
    CHECK (regexp_full_match(MOEDA, '[A-Z]{3}'))
)
"""

DDL_PRECOS_SUBSTITUICOES = """
CREATE TABLE IF NOT EXISTS precos_substituicoes (
    INSTRUMENTO_ID BIGINT NOT NULL,
    DATA DATE NOT NULL,

    TICKER_ORIGEM_ANTERIOR VARCHAR NOT NULL,
    ABERTURA_ANTERIOR DECIMAL(20,6),
    MAXIMA_ANTERIOR DECIMAL(20,6),
    MINIMA_ANTERIOR DECIMAL(20,6),
    PRECO_MEDIO_ANTERIOR DECIMAL(20,6),
    FECHAMENTO_ANTERIOR DECIMAL(20,6),
    QTD_NEGOCIOS_ANTERIOR BIGINT,
    QTD_TITULOS_ANTERIOR BIGINT,
    VOLUME_FINANCEIRO_ANTERIOR DECIMAL(24,2),
    MOEDA_ANTERIOR VARCHAR NOT NULL,
    FONTE_ANTERIOR VARCHAR NOT NULL,
    ARQUIVO_FONTE_ANTERIOR VARCHAR NOT NULL,

    TICKER_ORIGEM_NOVO VARCHAR NOT NULL,
    ABERTURA_NOVO DECIMAL(20,6),
    MAXIMA_NOVO DECIMAL(20,6),
    MINIMA_NOVO DECIMAL(20,6),
    PRECO_MEDIO_NOVO DECIMAL(20,6),
    FECHAMENTO_NOVO DECIMAL(20,6),
    QTD_NEGOCIOS_NOVO BIGINT,
    QTD_TITULOS_NOVO BIGINT,
    VOLUME_FINANCEIRO_NOVO DECIMAL(24,2),
    MOEDA_NOVO VARCHAR NOT NULL,
    FONTE_NOVO VARCHAR NOT NULL,
    ARQUIVO_FONTE_NOVO VARCHAR NOT NULL,

    SUBSTITUIDO_EM TIMESTAMP NOT NULL,
    MOTIVO VARCHAR NOT NULL,

    FOREIGN KEY (INSTRUMENTO_ID)
        REFERENCES instrumentos(INSTRUMENTO_ID)
)
"""


def conectar_mercado(
    database: DatabaseTarget | None = None,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """
    Abre o banco independente do dominio Mercado.

    O caminho padrao e data/processed/mercado.duckdb. Testes podem usar
    ':memory:' para nao tocar em nenhum artefato persistente.
    """
    alvo: DatabaseTarget = database if database is not None else MERCADO_DUCKDB

    if isinstance(alvo, Path):
        if read_only and not alvo.exists():
            raise FileNotFoundError(f"Banco de mercado nao existe: {alvo}")
        if not read_only:
            alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo_str = str(alvo)
    else:
        alvo_str = str(alvo)

    return duckdb.connect(database=alvo_str, read_only=read_only)


def criar_schema_identidade(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Cria somente o schema estrutural da D.2.
    """
    con.execute(DDL_INSTRUMENTOS)
    con.execute(DDL_IDENTIFICADORES)
    con.execute(DDL_TICKERS)


def criar_schema_precos(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Cria as estruturas de preços da D.3.

    Requer que o schema de identidade já exista.
    """
    con.execute(DDL_PRECOS_DIARIOS)
    con.execute(DDL_PRECOS_SUBSTITUICOES)


def criar_schema_mercado(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Cria o schema mínimo acumulado das fases D.2 e D.3.
    """
    criar_schema_identidade(con)
    criar_schema_precos(con)


def criar_banco_identidade(
    database: DatabaseTarget | None = None,
) -> Path:
    """
    Cria/atualiza apenas as tabelas D.2 no banco Mercado persistente.
    """
    alvo = Path(database) if database is not None else MERCADO_DUCKDB
    con = conectar_mercado(alvo, read_only=False)
    try:
        criar_schema_identidade(con)
    finally:
        con.close()
    return alvo


def criar_banco_mercado(
    database: DatabaseTarget | None = None,
) -> Path:
    """
    Cria/atualiza o schema mínimo acumulado D.2 + D.3.
    """
    alvo = Path(database) if database is not None else MERCADO_DUCKDB
    con = conectar_mercado(alvo, read_only=False)
    try:
        criar_schema_mercado(con)
    finally:
        con.close()
    return alvo

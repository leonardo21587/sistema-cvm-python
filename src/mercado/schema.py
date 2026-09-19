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

    Nao cria precos, proventos, eventos, benchmarks nem altera
    sistema_cvm.duckdb.
    """
    con.execute(DDL_INSTRUMENTOS)
    con.execute(DDL_IDENTIFICADORES)
    con.execute(DDL_TICKERS)


def criar_banco_identidade(
    database: DatabaseTarget | None = None,
) -> Path:
    """
    Cria/atualiza as tabelas D.2 no banco Mercado persistente.
    """
    alvo = Path(database) if database is not None else MERCADO_DUCKDB
    con = conectar_mercado(alvo, read_only=False)
    try:
        criar_schema_identidade(con)
    finally:
        con.close()
    return alvo

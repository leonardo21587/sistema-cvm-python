from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import duckdb

from src.mercado.identidade import (
    exigir_invariantes_identidade,
    normalizar_cd_cvm,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"


def _data(valor: str) -> date | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    return date.fromisoformat(valor)


def _ler_csv(nome: str, reference_dir: str | Path | None = None) -> list[dict[str, str]]:
    base = Path(reference_dir) if reference_dir is not None else REFERENCE_DIR
    caminho = base / nome

    if not caminho.is_file():
        raise FileNotFoundError(f"Catálogo de referência ausente: {caminho}")

    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def carregar_catalogo_referencia(
    con: duckdb.DuckDBPyConnection,
    *,
    reference_dir: str | Path | None = None,
    limpar_antes: bool = True,
) -> dict[str, int]:
    """
    Carrega o catálogo versionado de identidade no banco Mercado.

    Esta rotina não aloca novos INSTRUMENTO_ID. Ela apenas materializa
    IDs previamente definidos nos CSVs de referência.
    """
    instrumentos = _ler_csv("instrumentos.csv", reference_dir)
    tickers = _ler_csv("tickers_historico.csv", reference_dir)
    identificadores = _ler_csv("identificadores.csv", reference_dir)

    if limpar_antes:
        con.execute("DELETE FROM instrumentos_identificadores")
        con.execute("DELETE FROM tickers_historico")
        con.execute("DELETE FROM instrumentos")

    for linha in instrumentos:
        con.execute(
            """
            INSERT INTO instrumentos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                int(linha["INSTRUMENTO_ID"]),
                normalizar_cd_cvm(linha["CD_CVM"]),
                linha["TIPO_ATIVO"].strip().upper(),
                linha["CLASSE"].strip().upper(),
                linha["MOEDA"].strip().upper(),
                _data(linha["DT_INICIO"]),
                _data(linha["DT_FIM"]),
                linha["STATUS"].strip().upper(),
                linha["FONTE"].strip(),
            ],
        )

    for linha in identificadores:
        con.execute(
            """
            INSERT INTO instrumentos_identificadores VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                int(linha["INSTRUMENTO_ID"]),
                linha["TIPO_IDENTIFICADOR"].strip().upper(),
                linha["VALOR"].strip().upper(),
                _data(linha["DT_INICIO"]),
                _data(linha["DT_FIM"]),
                linha["FONTE"].strip(),
            ],
        )

    for linha in tickers:
        con.execute(
            """
            INSERT INTO tickers_historico VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                int(linha["INSTRUMENTO_ID"]),
                linha["BOLSA"].strip().upper(),
                linha["TICKER"].strip().upper(),
                _data(linha["DT_INICIO"]),
                _data(linha["DT_FIM"]),
                linha["STATUS"].strip().upper(),
                linha["FONTE"].strip(),
            ],
        )

    exigir_invariantes_identidade(con)

    return {
        "instrumentos": len(instrumentos),
        "identificadores": len(identificadores),
        "tickers": len(tickers),
    }


def tickers_catalogados(
    *,
    reference_dir: str | Path | None = None,
) -> set[str]:
    linhas = _ler_csv("tickers_historico.csv", reference_dir)
    return {
        linha["TICKER"].strip().upper()
        for linha in linhas
        if linha.get("TICKER")
    }

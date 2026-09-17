from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

PARQUET_DFP = PROCESSED_DIR / "dfp_2023_2025.parquet"
PARQUET_EMPRESAS = PROCESSED_DIR / "empresas.parquet"
BANCO_DUCKDB = PROCESSED_DIR / "sistema_cvm.duckdb"


def conectar(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """
    Abre conexão com o banco DuckDB persistente do projeto.
    """
    if read_only and not BANCO_DUCKDB.exists():
        raise FileNotFoundError(
            f"Banco DuckDB ainda não existe: {BANCO_DUCKDB}"
        )

    return duckdb.connect(
        database=str(BANCO_DUCKDB),
        read_only=read_only,
    )


def _validar_arquivos_origem() -> None:
    faltantes = [
        caminho
        for caminho in (PARQUET_DFP, PARQUET_EMPRESAS)
        if not caminho.exists()
    ]

    if faltantes:
        lista = "\n".join(str(c) for c in faltantes)
        raise FileNotFoundError(
            "Arquivos necessários não encontrados:\n"
            f"{lista}\n"
            "Execute primeiro o ETL em src/tratamento.py."
        )


def criar_banco() -> None:
    """
    Recria as tabelas do DuckDB a partir dos Parquets aprovados do ETL.
    """
    _validar_arquivos_origem()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    con = conectar(read_only=False)

    try:
        con.execute("DROP TABLE IF EXISTS dfp")
        con.execute("DROP TABLE IF EXISTS empresas")

        con.execute(
            """
            CREATE TABLE dfp AS
            SELECT *
            FROM read_parquet(?)
            """,
            [str(PARQUET_DFP)],
        )

        con.execute(
            """
            CREATE TABLE empresas AS
            SELECT *
            FROM read_parquet(?)
            """,
            [str(PARQUET_EMPRESAS)],
        )

        # Índices voltados aos filtros mais frequentes do sistema.
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dfp_empresa_ano_dem
            ON dfp (CD_CVM, ANO, DEMONSTRACAO)
            """
        )

        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dfp_conta
            ON dfp (CD_CVM, ANO, DEMONSTRACAO, CD_CONTA)
            """
        )

        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_empresas_cd_cvm
            ON empresas (CD_CVM)
            """
        )

        con.execute("ANALYZE")

    finally:
        con.close()


def validar_banco() -> dict[str, int]:
    """
    Confere os números básicos esperados após a construção do banco.
    """
    con = conectar(read_only=True)

    try:
        registros = con.execute(
            "SELECT COUNT(*) FROM dfp"
        ).fetchone()[0]

        empresas_dfp = con.execute(
            "SELECT COUNT(DISTINCT CD_CVM) FROM dfp"
        ).fetchone()[0]

        empresas_catalogo = con.execute(
            "SELECT COUNT(*) FROM empresas"
        ).fetchone()[0]

        conflitos = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    CD_CVM,
                    DEMONSTRACAO,
                    DT_INI_EXERC,
                    DT_FIM_EXERC,
                    CD_CONTA,
                    COUNT(*) AS n
                FROM dfp
                GROUP BY
                    CD_CVM,
                    DEMONSTRACAO,
                    DT_INI_EXERC,
                    DT_FIM_EXERC,
                    CD_CONTA
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

        return {
            "registros": int(registros),
            "empresas_dfp": int(empresas_dfp),
            "empresas_catalogo": int(empresas_catalogo),
            "conflitos": int(conflitos),
        }

    finally:
        con.close()


def buscar_empresas(
    termo: str = "",
    limite: int = 50,
) -> pd.DataFrame:
    """
    Pesquisa empresas por nome, CD_CVM ou CNPJ.

    A identificação operacional deve continuar baseada em CD_CVM/CNPJ;
    o nome serve para pesquisa e exibição.
    """
    termo = (termo or "").strip()
    limite = max(1, min(int(limite), 200))

    con = conectar(read_only=True)

    try:
        if not termo:
            return con.execute(
                """
                SELECT
                    CD_CVM,
                    CNPJ_CIA,
                    DENOM_CIA
                FROM empresas
                ORDER BY DENOM_CIA, CD_CVM
                LIMIT ?
                """,
                [limite],
            ).fetchdf()

        padrao = f"%{termo}%"
        termo_numerico = "".join(
            caractere for caractere in termo
            if caractere.isdigit()
        )

        return con.execute(
            """
            SELECT
                CD_CVM,
                CNPJ_CIA,
                DENOM_CIA
            FROM empresas
            WHERE
                DENOM_CIA ILIKE ?
                OR CD_CVM LIKE ?
                OR CNPJ_CIA LIKE ?
            ORDER BY
                CASE
                    WHEN CD_CVM = ? THEN 0
                    WHEN CNPJ_CIA = ? THEN 0
                    WHEN DENOM_CIA ILIKE ? THEN 1
                    ELSE 2
                END,
                DENOM_CIA,
                CD_CVM
            LIMIT ?
            """,
            [
                padrao,
                f"%{termo_numerico or termo}%",
                f"%{termo_numerico or termo}%",
                termo_numerico.zfill(6)
                if termo_numerico
                else termo,
                termo_numerico.zfill(14)
                if termo_numerico
                else termo,
                f"{termo}%",
                limite,
            ],
        ).fetchdf()

    finally:
        con.close()


def carregar_demonstracao(
    cd_cvm: str,
    ano: int,
    demonstracao: str,
) -> pd.DataFrame:
    """
    Retorna BPA, BPP ou DRE de uma empresa/exercício.
    """
    demonstracao = demonstracao.upper().strip()

    if demonstracao not in {"BPA", "BPP", "DRE"}:
        raise ValueError(
            "DEMONSTRACAO deve ser BPA, BPP ou DRE."
        )

    cd_cvm = str(cd_cvm).strip().zfill(6)
    ano = int(ano)

    con = conectar(read_only=True)

    try:
        return con.execute(
            """
            SELECT *
            FROM dfp
            WHERE
                CD_CVM = ?
                AND ANO = ?
                AND DEMONSTRACAO = ?
            ORDER BY CD_CONTA
            """,
            [cd_cvm, ano, demonstracao],
        ).fetchdf()

    finally:
        con.close()


def anos_disponiveis(cd_cvm: str) -> list[int]:
    cd_cvm = str(cd_cvm).strip().zfill(6)

    con = conectar(read_only=True)

    try:
        dados = con.execute(
            """
            SELECT DISTINCT ANO
            FROM dfp
            WHERE CD_CVM = ?
            ORDER BY ANO
            """,
            [cd_cvm],
        ).fetchall()

        return [int(linha[0]) for linha in dados]

    finally:
        con.close()


def main() -> None:
    print("=" * 70)
    print("SISTEMA CVM - DUCKDB")
    print("=" * 70)

    criar_banco()

    resumo = validar_banco()

    print()
    print("BANCO CRIADO COM SUCESSO")
    print(f"Arquivo: {BANCO_DUCKDB}")
    print(f"Registros: {resumo['registros']:,}")
    print(f"Empresas na DFP: {resumo['empresas_dfp']:,}")
    print(f"Empresas no catálogo: {resumo['empresas_catalogo']:,}")
    print(f"Conflitos: {resumo['conflitos']:,}")

    print()
    print("TESTE DE PESQUISA - VALE")
    print(
        buscar_empresas("VALE", limite=10).to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()

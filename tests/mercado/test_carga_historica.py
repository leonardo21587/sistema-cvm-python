from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

import duckdb


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.carga_historica import carregar_cotahist_catalogado  # noqa: E402
from src.mercado.schema import criar_schema_mercado  # noqa: E402


def _gravar(b, inicio, fim, valor):
    largura = fim - inicio + 1
    b[inicio - 1:fim] = list(str(valor).ljust(largura)[:largura])


def _num(b, inicio, fim, valor):
    largura = fim - inicio + 1
    b[inicio - 1:fim] = list(str(valor).zfill(largura))


def _linha(data, ticker, fechamento, isin):
    b = [" "] * 245
    _gravar(b, 1, 2, "01")
    _gravar(b, 3, 10, data)
    _gravar(b, 11, 12, "02")
    _gravar(b, 13, 24, ticker)
    _gravar(b, 25, 27, "010")
    _gravar(b, 28, 39, ticker)
    _gravar(b, 40, 49, "ON")
    _gravar(b, 53, 56, "R$")

    centavos = int(round(float(fechamento) * 100))
    for inicio, fim in [
        (57, 69), (70, 82), (83, 95), (96, 108), (109, 121),
        (122, 134), (135, 147),
    ]:
        _num(b, inicio, fim, centavos)

    _num(b, 148, 152, 10)
    _num(b, 153, 170, 1000)
    _num(b, 171, 188, centavos * 1000)
    _num(b, 189, 201, 0)
    _gravar(b, 202, 202, "0")
    _gravar(b, 203, 210, "00000000")
    _num(b, 211, 217, 1)
    _num(b, 218, 230, 0)
    _gravar(b, 231, 242, isin)
    _num(b, 243, 245, 1)
    return "".join(b)


def _header():
    return "00" + " " * 243


def _trailer():
    return "99" + " " * 243


def _zip_fixture(path: Path):
    conteudo = "\n".join([
        _header(),
        _linha("20240102", "PETR3", "38.00", "BRPETRACNOR9"),
        _linha("20240102", "IGNO3", "10.00", "BRTESTACNOR0"),
        _trailer(),
    ]) + "\n"

    with ZipFile(path, "w") as zf:
        zf.writestr("COTAHIST.2024.TXT", conteudo.encode("latin-1"))


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.4 — CARGA HISTÓRICA REUTILIZÁVEL")
    print("=" * 72)

    con = duckdb.connect(":memory:")
    try:
        criar_schema_mercado(con)

        con.execute(
            """
            INSERT INTO instrumentos VALUES
            (1001, '009512', 'ACAO', 'ON', 'BRL',
             DATE '2010-01-01', NULL, 'ATIVO', 'FIXTURE')
            """
        )
        con.execute(
            """
            INSERT INTO tickers_historico VALUES
            (1001, 'B3', 'PETR3', DATE '2010-01-01',
             NULL, 'VIGENTE', 'FIXTURE')
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "COTAHIST_A2024.ZIP"
            _zip_fixture(caminho)

            resultado = carregar_cotahist_catalogado(
                con,
                caminho,
                ano=2024,
            )

        assert resultado.linhas_cotacao == 2
        assert resultado.linhas_elegiveis == 1
        assert resultado.linhas_mapeadas == 1
        assert resultado.linhas_sem_instrumento == 0
        assert resultado.inseridos == 1
        assert resultado.por_ticker["PETR3"] == 1

    finally:
        con.close()

    print("RESULTADO: APROVADO")
    print("função anual reutilizável: aprovada")
    print("filtro catálogo + mercado à vista: aprovado")
    print("persistência via pipeline oficial: aprovada")


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.providers.b3_cotahist import (  # noqa: E402
    CotahistLayoutError,
    iterar_cotacoes_txt,
    iterar_cotacoes_zip,
    parse_registro_cotacao,
)


def _gravar(
    buffer: list[str],
    inicio: int,
    fim: int,
    valor: str,
) -> None:
    largura = fim - inicio + 1
    if len(valor) > largura:
        raise ValueError((inicio, fim, valor))
    texto = valor.ljust(largura)
    buffer[inicio - 1:fim] = list(texto)


def _gravar_numerico(
    buffer: list[str],
    inicio: int,
    fim: int,
    valor: int,
) -> None:
    largura = fim - inicio + 1
    texto = str(valor).zfill(largura)
    if len(texto) != largura:
        raise ValueError((inicio, fim, valor))
    buffer[inicio - 1:fim] = list(texto)


def _linha_cotacao() -> str:
    b = [" "] * 245

    _gravar(b, 1, 2, "01")
    _gravar(b, 3, 10, "20250919")
    _gravar(b, 11, 12, "02")
    _gravar(b, 13, 24, "VALE3")
    _gravar(b, 25, 27, "010")
    _gravar(b, 28, 39, "VALE")
    _gravar(b, 40, 49, "ON")
    _gravar(b, 50, 52, "")
    _gravar(b, 53, 56, "R$")

    # Campos (11)V99: largura total 13, duas casas implícitas.
    _gravar_numerico(b, 57, 69, 6012)
    _gravar_numerico(b, 70, 82, 6150)
    _gravar_numerico(b, 83, 95, 5988)
    _gravar_numerico(b, 96, 108, 6066)
    _gravar_numerico(b, 109, 121, 6101)
    _gravar_numerico(b, 122, 134, 6100)
    _gravar_numerico(b, 135, 147, 6102)

    _gravar_numerico(b, 148, 152, 1234)
    _gravar_numerico(b, 153, 170, 9876543)
    _gravar_numerico(b, 171, 188, 60000012345)

    _gravar_numerico(b, 189, 201, 0)
    _gravar(b, 202, 202, "0")
    _gravar(b, 203, 210, "00000000")
    _gravar_numerico(b, 211, 217, 1)
    _gravar_numerico(b, 218, 230, 0)
    _gravar(b, 231, 242, "BRVALEACNOR0")
    _gravar_numerico(b, 243, 245, 123)

    linha = "".join(b)
    assert len(linha) == 245
    return linha


def _linha_header() -> str:
    b = [" "] * 245
    _gravar(b, 1, 2, "00")
    _gravar(b, 3, 15, "COTAHIST.2025")
    _gravar(b, 16, 23, "BOVESPA")
    _gravar(b, 24, 31, "20250919")
    return "".join(b)


def _linha_trailer() -> str:
    b = [" "] * 245
    _gravar(b, 1, 2, "99")
    _gravar(b, 3, 15, "COTAHIST.2025")
    _gravar(b, 16, 23, "BOVESPA")
    _gravar(b, 24, 31, "20250919")
    _gravar_numerico(b, 32, 42, 3)
    return "".join(b)


def teste_parse_registro_01():
    cotacao = parse_registro_cotacao(_linha_cotacao())

    assert cotacao.data == date(2025, 9, 19)
    assert cotacao.cod_bdi == "02"
    assert cotacao.ticker == "VALE3"
    assert cotacao.tipo_mercado == "010"
    assert cotacao.nome_resumido == "VALE"
    assert cotacao.especificacao == "ON"
    assert cotacao.moeda_referencia == "R$"

    assert cotacao.abertura == Decimal("60.12")
    assert cotacao.maxima == Decimal("61.50")
    assert cotacao.minima == Decimal("59.88")
    assert cotacao.preco_medio == Decimal("60.66")
    assert cotacao.fechamento == Decimal("61.01")
    assert cotacao.melhor_oferta_compra == Decimal("61.00")
    assert cotacao.melhor_oferta_venda == Decimal("61.02")

    assert cotacao.qtd_negocios == 1234
    assert cotacao.qtd_titulos == 9876543
    assert cotacao.volume_financeiro == Decimal("600000123.45")
    assert cotacao.preco_exercicio == Decimal("0.00")
    assert cotacao.data_vencimento is None
    assert cotacao.fator_cotacao == 1
    assert cotacao.preco_exercicio_pontos == Decimal("0.000000")
    assert cotacao.isin == "BRVALEACNOR0"
    assert cotacao.numero_distribuicao == 123


def teste_txt_header_e_trailer_ignorados():
    conteudo = "\n".join([
        _linha_header(),
        _linha_cotacao(),
        _linha_trailer(),
    ]) + "\n"

    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "COTAHIST.2025.TXT"
        caminho.write_text(conteudo, encoding="latin-1", newline="")

        registros = list(iterar_cotacoes_txt(caminho))

    assert len(registros) == 1
    assert registros[0].ticker == "VALE3"


def teste_zip_sem_extracao():
    conteudo = "\n".join([
        _linha_header(),
        _linha_cotacao(),
        _linha_trailer(),
    ]) + "\n"

    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "COTAHIST_A2025.ZIP"

        with ZipFile(caminho, "w") as zf:
            zf.writestr(
                "COTAHIST.2025.TXT",
                conteudo.encode("latin-1"),
            )

        registros = list(iterar_cotacoes_zip(caminho))

    assert len(registros) == 1
    assert registros[0].fechamento == Decimal("61.01")


def teste_tamanho_invalido_bloqueia():
    try:
        parse_registro_cotacao("01" + " " * 10)
    except CotahistLayoutError:
        pass
    else:
        raise AssertionError("Registro fora de 245 posições deveria bloquear.")


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.3 — PARSER B3 COTAHIST")
    print("=" * 72)

    teste_parse_registro_01()
    teste_txt_header_e_trailer_ignorados()
    teste_zip_sem_extracao()
    teste_tamanho_invalido_bloqueia()

    print("RESULTADO: APROVADO")
    print("Layout 245 posições: aprovado")
    print("Preços com 2 casas implícitas: aprovado")
    print("TXT e ZIP: aprovados")
    print("Header/trailer: tratados sem contaminar cotações")


if __name__ == "__main__":
    main()

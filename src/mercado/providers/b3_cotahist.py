from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile


TAMANHO_REGISTRO = 245
TIPO_HEADER = "00"
TIPO_COTACAO = "01"
TIPO_TRAILER = "99"


class CotahistLayoutError(ValueError):
    """Linha COTAHIST incompatível com o layout oficial esperado."""


@dataclass(frozen=True)
class CotacaoB3:
    data: date
    cod_bdi: str
    ticker: str
    tipo_mercado: str
    nome_resumido: str
    especificacao: str
    prazo_termo: str | None
    moeda_referencia: str
    abertura: Decimal | None
    maxima: Decimal | None
    minima: Decimal | None
    preco_medio: Decimal | None
    fechamento: Decimal | None
    melhor_oferta_compra: Decimal | None
    melhor_oferta_venda: Decimal | None
    qtd_negocios: int | None
    qtd_titulos: int | None
    volume_financeiro: Decimal | None
    preco_exercicio: Decimal | None
    indicador_correcao: str | None
    data_vencimento: date | None
    fator_cotacao: int | None
    preco_exercicio_pontos: Decimal | None
    isin: str | None
    numero_distribuicao: int | None


def _campo(linha: str, inicio: int, fim: int) -> str:
    """Recorta posições 1-based inclusivas do layout B3."""
    return linha[inicio - 1:fim]


def _texto(linha: str, inicio: int, fim: int) -> str:
    return _campo(linha, inicio, fim).strip()


def _inteiro(texto: str) -> int | None:
    valor = texto.strip()
    if not valor:
        return None
    if not valor.isdigit():
        raise CotahistLayoutError(f"Campo inteiro inválido: {texto!r}")
    return int(valor)


def _decimal_implicito(texto: str, casas: int) -> Decimal | None:
    valor = texto.strip()
    if not valor:
        return None
    if not valor.isdigit():
        raise CotahistLayoutError(f"Campo decimal inválido: {texto!r}")

    return Decimal(int(valor)).scaleb(-casas)


def _data_aaaammdd(
    texto: str,
    *,
    obrigatoria: bool,
) -> date | None:
    valor = texto.strip()

    if not valor or valor == "00000000":
        if obrigatoria:
            raise CotahistLayoutError("Data obrigatória ausente no registro.")
        return None

    if len(valor) != 8 or not valor.isdigit():
        raise CotahistLayoutError(f"Data inválida: {texto!r}")

    try:
        return datetime.strptime(valor, "%Y%m%d").date()
    except ValueError as exc:
        raise CotahistLayoutError(f"Data inválida: {texto!r}") from exc


def validar_linha_cotahist(linha: str) -> str:
    """
    Remove apenas quebra de linha e valida o tamanho fixo de 245 bytes/caracteres.

    Os campos do layout são ASCII; por isso, após decodificação Latin-1,
    as posições permanecem alinhadas byte a byte.
    """
    limpa = linha.rstrip("\r\n")

    if len(limpa) != TAMANHO_REGISTRO:
        raise CotahistLayoutError(
            f"Registro com {len(limpa)} caracteres; esperado {TAMANHO_REGISTRO}."
        )

    return limpa


def parse_registro_cotacao(linha: str) -> CotacaoB3:
    """
    Interpreta registro 01 do COTAHIST conforme layout B3 de 245 posições.
    """
    linha = validar_linha_cotahist(linha)

    if _campo(linha, 1, 2) != TIPO_COTACAO:
        raise CotahistLayoutError("Registro informado não é do tipo 01.")

    return CotacaoB3(
        data=_data_aaaammdd(_campo(linha, 3, 10), obrigatoria=True),
        cod_bdi=_texto(linha, 11, 12),
        ticker=_texto(linha, 13, 24),
        tipo_mercado=_texto(linha, 25, 27),
        nome_resumido=_texto(linha, 28, 39),
        especificacao=_texto(linha, 40, 49),
        prazo_termo=_texto(linha, 50, 52) or None,
        moeda_referencia=_texto(linha, 53, 56),
        abertura=_decimal_implicito(_campo(linha, 57, 69), 2),
        maxima=_decimal_implicito(_campo(linha, 70, 82), 2),
        minima=_decimal_implicito(_campo(linha, 83, 95), 2),
        preco_medio=_decimal_implicito(_campo(linha, 96, 108), 2),
        fechamento=_decimal_implicito(_campo(linha, 109, 121), 2),
        melhor_oferta_compra=_decimal_implicito(_campo(linha, 122, 134), 2),
        melhor_oferta_venda=_decimal_implicito(_campo(linha, 135, 147), 2),
        qtd_negocios=_inteiro(_campo(linha, 148, 152)),
        qtd_titulos=_inteiro(_campo(linha, 153, 170)),
        volume_financeiro=_decimal_implicito(_campo(linha, 171, 188), 2),
        preco_exercicio=_decimal_implicito(_campo(linha, 189, 201), 2),
        indicador_correcao=_texto(linha, 202, 202) or None,
        data_vencimento=_data_aaaammdd(
            _campo(linha, 203, 210),
            obrigatoria=False,
        ),
        fator_cotacao=_inteiro(_campo(linha, 211, 217)),
        preco_exercicio_pontos=_decimal_implicito(
            _campo(linha, 218, 230),
            6,
        ),
        isin=_texto(linha, 231, 242) or None,
        numero_distribuicao=_inteiro(_campo(linha, 243, 245)),
    )


def iterar_cotacoes_txt(
    caminho: str | Path,
    *,
    encoding: str = "latin-1",
) -> Iterator[CotacaoB3]:
    """
    Itera apenas registros 01 de um COTAHIST TXT.
    Header (00) e trailer (99) são validados em tamanho e ignorados.
    """
    caminho = Path(caminho)

    with caminho.open("r", encoding=encoding, newline="") as arquivo:
        for numero_linha, linha in enumerate(arquivo, start=1):
            try:
                limpa = validar_linha_cotahist(linha)
            except CotahistLayoutError as exc:
                raise CotahistLayoutError(
                    f"{caminho.name}: linha {numero_linha}: {exc}"
                ) from exc

            tipo = _campo(limpa, 1, 2)

            if tipo == TIPO_COTACAO:
                yield parse_registro_cotacao(limpa)
            elif tipo in {TIPO_HEADER, TIPO_TRAILER}:
                continue
            else:
                raise CotahistLayoutError(
                    f"{caminho.name}: linha {numero_linha}: "
                    f"tipo de registro desconhecido {tipo!r}."
                )


def iterar_cotacoes_zip(
    caminho: str | Path,
    *,
    encoding: str = "latin-1",
) -> Iterator[CotacaoB3]:
    """
    Itera registros 01 diretamente de um ZIP anual da B3 sem extrair em disco.
    """
    caminho = Path(caminho)

    with ZipFile(caminho) as zip_file:
        candidatos = [
            nome
            for nome in zip_file.namelist()
            if nome.upper().endswith(".TXT")
        ]

        if len(candidatos) != 1:
            raise CotahistLayoutError(
                f"{caminho.name}: esperado exatamente 1 TXT; "
                f"encontrados {len(candidatos)}."
            )

        nome_txt = candidatos[0]

        with zip_file.open(nome_txt, "r") as arquivo_binario:
            for numero_linha, bruto in enumerate(arquivo_binario, start=1):
                linha = bruto.decode(encoding)

                try:
                    limpa = validar_linha_cotahist(linha)
                except CotahistLayoutError as exc:
                    raise CotahistLayoutError(
                        f"{caminho.name}/{nome_txt}: linha {numero_linha}: {exc}"
                    ) from exc

                tipo = _campo(limpa, 1, 2)

                if tipo == TIPO_COTACAO:
                    yield parse_registro_cotacao(limpa)
                elif tipo in {TIPO_HEADER, TIPO_TRAILER}:
                    continue
                else:
                    raise CotahistLayoutError(
                        f"{caminho.name}/{nome_txt}: linha {numero_linha}: "
                        f"tipo de registro desconhecido {tipo!r}."
                    )


def iterar_cotacoes(caminho: str | Path) -> Iterator[CotacaoB3]:
    caminho = Path(caminho)

    if caminho.suffix.lower() == ".zip":
        yield from iterar_cotacoes_zip(caminho)
        return

    if caminho.suffix.lower() == ".txt":
        yield from iterar_cotacoes_txt(caminho)
        return

    raise ValueError(
        f"Formato não suportado para COTAHIST: {caminho.suffix!r}"
    )

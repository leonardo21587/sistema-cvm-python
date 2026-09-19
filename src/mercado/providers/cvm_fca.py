from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import requests

from src.mercado.arquivos import calcular_sha256
from src.mercado.identidade import normalizar_cd_cvm


ROOT_DIR = Path(__file__).resolve().parents[3]
FCA_RAW_DIR = ROOT_DIR / "data" / "market" / "raw" / "cvm" / "fca"
FCA_URL = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/"
    "fca_cia_aberta_{ano}.zip"
)

TICKER_ACAO_RE = re.compile(r"^[A-Z0-9]{4}[3-8]$")
TICKER_UNIT_RE = re.compile(r"^[A-Z0-9]{4}11$")


@dataclass(frozen=True)
class FcaValorMobiliario:
    cd_cvm: str | None
    cnpj: str
    data_referencia: date | None
    versao: int | None
    id_documento: str
    nome_empresarial: str
    valor_mobiliario: str
    sigla_classe_preferencial: str
    classe_preferencial: str
    codigo_negociacao: str
    composicao_bdr_unit: str
    mercado: str
    sigla_entidade_administradora: str
    entidade_administradora: str
    data_inicio_negociacao: date | None
    data_fim_negociacao: date | None
    segmento: str
    data_inicio_listagem: date | None
    data_fim_listagem: date | None


def _texto(valor: object) -> str:
    return "" if valor is None else str(valor).strip()


def _cnpj(valor: object) -> str:
    digitos = "".join(ch for ch in _texto(valor) if ch.isdigit())
    return digitos.zfill(14) if digitos else ""


def _data_iso(valor: object) -> date | None:
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        return None


def _inteiro(valor: object) -> int | None:
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except ValueError:
        return None


def ticker_formato_elegivel(ticker: str) -> bool:
    ticker = _texto(ticker).upper()
    return bool(TICKER_ACAO_RE.fullmatch(ticker) or TICKER_UNIT_RE.fullmatch(ticker))


def baixar_fca(
    ano: int,
    *,
    destino: str | Path | None = None,
    timeout: tuple[int, int] = (10, 120),
) -> Path:
    """
    Baixa o ZIP anual oficial do FCA da CVM de forma atômica.

    Se o arquivo já existir, ele é reutilizado; o diagnóstico registra o
    SHA-256 para rastreabilidade.
    """
    ano = int(ano)
    if destino is None:
        destino = FCA_RAW_DIR / str(ano) / f"fca_cia_aberta_{ano}.zip"
    destino = Path(destino)

    if destino.is_file() and destino.stat().st_size > 0:
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    url = FCA_URL.format(ano=ano)

    resposta = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "Sistema-CVM-Academico/1.0"},
    )
    resposta.raise_for_status()

    if not resposta.content:
        raise RuntimeError(f"FCA {ano}: resposta vazia da CVM.")

    if not zipfile.is_zipfile(io.BytesIO(resposta.content)):
        raise RuntimeError(f"FCA {ano}: resposta não é um ZIP válido.")

    temporario.write_bytes(resposta.content)
    temporario.replace(destino)
    return destino


def _abrir_csv_do_zip(
    zip_file: zipfile.ZipFile,
    nome: str,
) -> Iterable[dict[str, str]]:
    try:
        bruto = zip_file.read(nome)
    except KeyError as exc:
        raise RuntimeError(f"Arquivo {nome!r} ausente no ZIP FCA.") from exc

    texto = bruto.decode("latin-1")
    return csv.DictReader(io.StringIO(texto), delimiter=";")


def _mapa_cnpj_cd_cvm(
    zip_file: zipfile.ZipFile,
    ano: int,
) -> tuple[dict[str, str], dict[str, set[str]]]:
    nome = f"fca_cia_aberta_{ano}.csv"
    candidatos: dict[str, set[str]] = {}

    for linha in _abrir_csv_do_zip(zip_file, nome):
        cnpj = _cnpj(linha.get("CNPJ_CIA"))
        cd_raw = _texto(linha.get("CD_CVM"))

        if not cnpj or not cd_raw:
            continue

        try:
            cd_cvm = normalizar_cd_cvm(cd_raw)
        except ValueError:
            continue

        candidatos.setdefault(cnpj, set()).add(cd_cvm)

    mapa: dict[str, str] = {}
    ambiguos: dict[str, set[str]] = {}

    for cnpj, codigos in candidatos.items():
        if len(codigos) == 1:
            mapa[cnpj] = next(iter(codigos))
        else:
            ambiguos[cnpj] = codigos

    return mapa, ambiguos


def ler_fca_valores_mobiliarios(
    caminho_zip: str | Path,
    *,
    ano: int,
) -> tuple[list[FcaValorMobiliario], dict[str, set[str]]]:
    """
    Lê o arquivo estruturado valor_mobiliario do FCA e resolve CD_CVM por CNPJ.

    Nenhum ticker é considerado verdadeiro apenas por estar no FCA; a
    confirmação contra COTAHIST acontece na etapa de diagnóstico.
    """
    caminho_zip = Path(caminho_zip)
    if not caminho_zip.is_file():
        raise FileNotFoundError(caminho_zip)

    ano = int(ano)
    nome_vm = f"fca_cia_aberta_valor_mobiliario_{ano}.csv"

    with zipfile.ZipFile(caminho_zip) as zf:
        mapa, ambiguos = _mapa_cnpj_cd_cvm(zf, ano)
        linhas = list(_abrir_csv_do_zip(zf, nome_vm))

    saida: list[FcaValorMobiliario] = []
    chaves_vistas: set[tuple] = set()

    for linha in linhas:
        cnpj = _cnpj(linha.get("CNPJ_Companhia"))
        ticker = _texto(linha.get("Codigo_Negociacao")).upper()

        registro = FcaValorMobiliario(
            cd_cvm=mapa.get(cnpj),
            cnpj=cnpj,
            data_referencia=_data_iso(linha.get("Data_Referencia")),
            versao=_inteiro(linha.get("Versao")),
            id_documento=_texto(linha.get("ID_Documento")),
            nome_empresarial=_texto(linha.get("Nome_Empresarial")),
            valor_mobiliario=_texto(linha.get("Valor_Mobiliario")),
            sigla_classe_preferencial=_texto(
                linha.get("Sigla_Classe_Acao_Preferencial")
            ),
            classe_preferencial=_texto(
                linha.get("Classe_Acao_Preferencial")
            ),
            codigo_negociacao=ticker,
            composicao_bdr_unit=_texto(linha.get("Composicao_BDR_Unit")),
            mercado=_texto(linha.get("Mercado")),
            sigla_entidade_administradora=_texto(
                linha.get("Sigla_Entidade_Administradora")
            ),
            entidade_administradora=_texto(
                linha.get("Entidade_Administradora")
            ),
            data_inicio_negociacao=_data_iso(
                linha.get("Data_Inicio_Negociacao")
            ),
            data_fim_negociacao=_data_iso(
                linha.get("Data_Fim_Negociacao")
            ),
            segmento=_texto(linha.get("Segmento")),
            data_inicio_listagem=_data_iso(
                linha.get("Data_Inicio_Listagem")
            ),
            data_fim_listagem=_data_iso(
                linha.get("Data_Fim_Listagem")
            ),
        )

        chave = (
            registro.cd_cvm,
            registro.cnpj,
            registro.codigo_negociacao,
            registro.data_inicio_negociacao,
            registro.data_fim_negociacao,
            registro.valor_mobiliario,
            registro.sigla_classe_preferencial,
            registro.composicao_bdr_unit,
        )

        if chave in chaves_vistas:
            continue

        chaves_vistas.add(chave)
        saida.append(registro)

    return saida, ambiguos


def sha256_fca(caminho_zip: str | Path) -> str:
    return calcular_sha256(caminho_zip)

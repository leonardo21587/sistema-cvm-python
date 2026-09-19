from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from src.mercado.arquivos import calcular_sha256


ROOT_DIR = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT_DIR / "data" / "market" / "raw" / "b3" / "companhias"

BASE = (
    "https://sistemaswebb3-listados.b3.com.br/"
    "listedCompaniesProxy/CompanyCall"
)
URL_LISTA = f"{BASE}/GetInitialCompanies"
URL_DETALHE = f"{BASE}/GetDetail"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
}


@dataclass(frozen=True)
class CompanhiaB3:
    cd_cvm: str
    cnpj: str
    issuing_company: str
    company_name: str
    trading_name: str


@dataclass(frozen=True)
class CodigoB3:
    ticker: str
    isin: str


@dataclass(frozen=True)
class DetalheCompanhiaB3:
    cd_cvm: str
    cnpj: str
    issuing_company: str
    company_name: str
    trading_name: str
    codigos: tuple[CodigoB3, ...]


def _normalizar_cd_cvm(valor: object) -> str:
    digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
    return digitos.zfill(6) if digitos else ""


def _normalizar_cnpj(valor: object) -> str:
    digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
    return digitos.zfill(14) if digitos else ""


def _payload_b64(payload: dict) -> str:
    bruto = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.b64encode(bruto).decode("ascii")


def _get_json(
    url_base: str,
    payload: dict,
    *,
    timeout: tuple[int, int] = (10, 120),
    tentativas: int = 3,
) -> object:
    url = f"{url_base}/{_payload_b64(payload)}"
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
            )
            resposta.raise_for_status()
            return resposta.json()
        except Exception as exc:
            ultimo_erro = exc
            if tentativa < tentativas:
                time.sleep(1.5 * tentativa)

    raise RuntimeError(
        f"Falha ao consultar B3 após {tentativas} tentativa(s): "
        f"{ultimo_erro}"
    )


def listar_companhias_b3(
    *,
    page_size: int = 120,
    usar_cache: bool = True,
) -> tuple[list[CompanhiaB3], Path]:
    """
    Lista companhias da API pública da B3 e preserva o JSON bruto em cache.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = RAW_DIR / "listed_companies.json"

    if usar_cache and cache.is_file():
        dados = json.loads(cache.read_text(encoding="utf-8"))
    else:
        resultados = []
        pagina = 1
        total_paginas = 1

        while pagina <= total_paginas:
            objeto = _get_json(
                URL_LISTA,
                {
                    "language": "pt-br",
                    "pageNumber": pagina,
                    "pageSize": int(page_size),
                },
            )

            if not isinstance(objeto, dict):
                raise RuntimeError(
                    "Resposta inesperada da lista de companhias B3."
                )

            resultados.extend(objeto.get("results") or [])
            pagina_info = objeto.get("page") or {}
            total_paginas = int(
                pagina_info.get("totalPages") or pagina
            )
            pagina += 1
            time.sleep(0.20)

        dados = {
            "results": resultados,
        }
        cache.write_text(
            json.dumps(
                dados,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    saida = []
    for item in dados.get("results") or []:
        cd_cvm = _normalizar_cd_cvm(
            item.get("codeCVM")
            or item.get("codeCvm")
            or item.get("code")
        )
        if not cd_cvm:
            continue

        saida.append(
            CompanhiaB3(
                cd_cvm=cd_cvm,
                cnpj=_normalizar_cnpj(item.get("cnpj")),
                issuing_company=str(
                    item.get("issuingCompany") or ""
                ).strip().upper(),
                company_name=str(
                    item.get("companyName") or ""
                ).strip(),
                trading_name=str(
                    item.get("tradingName") or ""
                ).strip(),
            )
        )

    return saida, cache


def detalhar_companhia_b3(
    cd_cvm: str,
    *,
    usar_cache: bool = True,
) -> tuple[DetalheCompanhiaB3 | None, Path]:
    """
    Consulta GetDetail por CD_CVM e expande otherCodes (ticker + ISIN).
    """
    cd_cvm = _normalizar_cd_cvm(cd_cvm)
    if not cd_cvm:
        raise ValueError("CD_CVM inválido.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = RAW_DIR / f"detail_{cd_cvm}.json"

    if usar_cache and cache.is_file():
        objeto = json.loads(cache.read_text(encoding="utf-8"))
    else:
        objeto = _get_json(
            URL_DETALHE,
            {
                "codeCVM": cd_cvm,
                "language": "pt-br",
            },
        )
        cache.write_text(
            json.dumps(
                objeto,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if isinstance(objeto, list):
        if not objeto:
            return None, cache
        raiz = objeto[0]
    elif isinstance(objeto, dict):
        raiz = objeto
    else:
        return None, cache

    if not raiz:
        return None, cache

    codigos = []
    vistos = set()

    for item in raiz.get("otherCodes") or []:
        ticker = str(item.get("code") or "").strip().upper()
        isin = str(item.get("isin") or "").strip().upper()
        if not ticker:
            continue
        chave = (ticker, isin)
        if chave in vistos:
            continue
        vistos.add(chave)
        codigos.append(CodigoB3(ticker=ticker, isin=isin))

    detalhe = DetalheCompanhiaB3(
        cd_cvm=_normalizar_cd_cvm(
            raiz.get("codeCVM")
            or raiz.get("codeCvm")
            or cd_cvm
        ),
        cnpj=_normalizar_cnpj(raiz.get("cnpj")),
        issuing_company=str(
            raiz.get("issuingCompany") or ""
        ).strip().upper(),
        company_name=str(
            raiz.get("companyName") or ""
        ).strip(),
        trading_name=str(
            raiz.get("tradingName") or ""
        ).strip(),
        codigos=tuple(sorted(
            codigos,
            key=lambda x: (x.ticker, x.isin),
        )),
    )
    return detalhe, cache


def sha256_cache(caminho: str | Path) -> str:
    return calcular_sha256(caminho)

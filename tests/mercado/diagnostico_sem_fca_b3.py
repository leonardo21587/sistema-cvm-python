from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.providers.b3_companhias import (  # noqa: E402
    detalhar_companhia_b3,
    listar_companhias_b3,
    sha256_cache,
)


REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
UNIVERSO = REPORTS_DIR / "universo_ampliado_2025_tickers.csv"
SAIDA = REPORTS_DIR / "universo_ampliado_2025_sem_fca_b3.csv"


def _digitos(valor: object) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def _ler(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def _escrever(caminho: Path, linhas: list[dict], campos: list[str]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=campos,
            delimiter=";",
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def _catalogo_sistema() -> dict[str, dict[str, str]]:
    con = conectar_cvm(read_only=True)
    try:
        linhas = con.execute(
            """
            SELECT CD_CVM, CNPJ_CIA, DENOM_CIA
            FROM empresas
            ORDER BY CD_CVM
            """
        ).fetchall()
    finally:
        con.close()

    return {
        str(cd_cvm).strip().zfill(6): {
            "cnpj": _digitos(cnpj).zfill(14),
            "nome": str(nome or "").strip(),
        }
        for cd_cvm, cnpj, nome in linhas
    }


def main() -> None:
    universo = _ler(UNIVERSO)
    sistema = _catalogo_sistema()

    sem_fca = [
        linha
        for linha in universo
        if linha["STATUS"] == "REVISAO"
        and linha["MOTIVO"] == "SEM_FCA"
    ]

    print("=" * 92)
    print("SISTEMA CVM — D.4 — RESOLUÇÃO SEM_FCA VIA B3")
    print("=" * 92)
    print(f"Tickers SEM_FCA recebidos: {len(sem_fca):,}")

    companhias, cache_lista = listar_companhias_b3()

    por_raiz: dict[str, list] = defaultdict(list)
    for companhia in companhias:
        raiz = companhia.issuing_company.strip().upper()
        if raiz:
            por_raiz[raiz].append(companhia)

    resolvidos = []
    ambiguos = []
    sem_candidato = []
    fora_sistema = []
    divergencias = []

    detalhes_cache = {}

    for linha in sorted(sem_fca, key=lambda x: x["TICKER"]):
        ticker = linha["TICKER"].strip().upper()
        raiz = ticker[:4]
        candidatos = por_raiz.get(raiz, [])

        if not candidatos:
            sem_candidato.append({
                "TICKER": ticker,
                "RAIZ": raiz,
                "STATUS": "SEM_CANDIDATO_B3",
                "CD_CVM": "",
                "CNPJ_B3": "",
                "ISIN_B3": "",
                "DETALHE": "",
            })
            continue

        codigos = sorted({x.cd_cvm for x in candidatos if x.cd_cvm})
        if len(codigos) > 1:
            ambiguos.append({
                "TICKER": ticker,
                "RAIZ": raiz,
                "STATUS": "AMBIGUO_RAIZ_B3",
                "CD_CVM": "|".join(codigos),
                "CNPJ_B3": "",
                "ISIN_B3": "",
                "DETALHE": "",
            })
            continue

        cd_cvm = codigos[0]
        if cd_cvm not in sistema:
            fora_sistema.append({
                "TICKER": ticker,
                "RAIZ": raiz,
                "STATUS": "CD_CVM_B3_FORA_SISTEMA",
                "CD_CVM": cd_cvm,
                "CNPJ_B3": "",
                "ISIN_B3": "",
                "DETALHE": "",
            })
            continue

        if cd_cvm not in detalhes_cache:
            detalhes_cache[cd_cvm] = detalhar_companhia_b3(cd_cvm)

        detalhe, cache = detalhes_cache[cd_cvm]
        if detalhe is None:
            sem_candidato.append({
                "TICKER": ticker,
                "RAIZ": raiz,
                "STATUS": "SEM_DETALHE_B3",
                "CD_CVM": cd_cvm,
                "CNPJ_B3": "",
                "ISIN_B3": "",
                "DETALHE": "",
            })
            continue

        codigos_exatos = [
            codigo
            for codigo in detalhe.codigos
            if codigo.ticker == ticker
        ]

        if not codigos_exatos:
            sem_candidato.append({
                "TICKER": ticker,
                "RAIZ": raiz,
                "STATUS": "TICKER_NAO_ENCONTRADO_NO_GETDETAIL",
                "CD_CVM": cd_cvm,
                "CNPJ_B3": detalhe.cnpj,
                "ISIN_B3": "",
                "DETALHE": "|".join(
                    codigo.ticker for codigo in detalhe.codigos
                ),
            })
            continue

        cnpj_sistema = sistema[cd_cvm]["cnpj"]
        cnpj_b3 = detalhe.cnpj

        if cnpj_b3 and cnpj_sistema and cnpj_b3 != cnpj_sistema:
            divergencias.append({
                "TICKER": ticker,
                "RAIZ": raiz,
                "STATUS": "CNPJ_DIVERGENTE",
                "CD_CVM": cd_cvm,
                "CNPJ_B3": cnpj_b3,
                "ISIN_B3": "|".join(
                    sorted({x.isin for x in codigos_exatos if x.isin})
                ),
                "DETALHE": f"CNPJ_SISTEMA={cnpj_sistema}",
            })
            continue

        resolvidos.append({
            "TICKER": ticker,
            "RAIZ": raiz,
            "STATUS": "RESOLVIDO_B3_EXATO",
            "CD_CVM": cd_cvm,
            "CNPJ_B3": cnpj_b3,
            "ISIN_B3": "|".join(
                sorted({x.isin for x in codigos_exatos if x.isin})
            ),
            "DETALHE": sistema[cd_cvm]["nome"],
        })

    saida = (
        resolvidos
        + ambiguos
        + sem_candidato
        + fora_sistema
        + divergencias
    )

    _escrever(
        SAIDA,
        sorted(saida, key=lambda x: (x["STATUS"], x["TICKER"])),
        [
            "TICKER",
            "RAIZ",
            "STATUS",
            "CD_CVM",
            "CNPJ_B3",
            "ISIN_B3",
            "DETALHE",
        ],
    )

    print()
    print("RESUMO")
    print("-" * 92)
    print(f"Companhias retornadas pela B3: {len(companhias):,}")
    print(f"Resolvidos por ticker exato no GetDetail: {len(resolvidos):,}")
    print(f"Raiz B3 ambígua: {len(ambiguos):,}")
    print(f"Sem candidato/detalhe exato: {len(sem_candidato):,}")
    print(f"CD_CVM B3 fora das 499 empresas: {len(fora_sistema):,}")
    print(f"Divergências de CNPJ: {len(divergencias):,}")
    print()

    if resolvidos:
        print("RESOLVIDOS")
        print("-" * 92)
        for item in resolvidos:
            print(
                f"{item['TICKER']:8s} | {item['CD_CVM']} | "
                f"{item['ISIN_B3']:14s} | {item['DETALHE']}"
            )
        print()

    pendentes = ambiguos + sem_candidato + fora_sistema + divergencias
    if pendentes:
        print("PENDENTES")
        print("-" * 92)
        for item in pendentes:
            print(
                f"{item['TICKER']:8s} | {item['STATUS']:32s} | "
                f"{item['CD_CVM']:12s} | {item['DETALHE']}"
            )
        print()

    print(f"Cache lista B3: {cache_lista}")
    print(f"SHA-256 lista B3: {sha256_cache(cache_lista)}")
    print(f"Relatório: {SAIDA}")
    print()
    print("RESULTADO: DIAGNÓSTICO CONCLUÍDO")
    print(
        "Nenhum CSV oficial de referência e nenhum INSTRUMENTO_ID "
        "foram alterados."
    )


if __name__ == "__main__":
    main()

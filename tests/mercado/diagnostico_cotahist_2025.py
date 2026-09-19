from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.arquivos import preservar_arquivo_raw  # noqa: E402
from src.mercado.providers.b3_cotahist import iterar_cotacoes  # noqa: E402


TICKERS_AUDITORIA = {
    "PETR3",
    "PETR4",
    "TAEE11",
    "MGLU3",
    "ELET3",
    "AXIA3",
    "NATU3",
    "NTCO3",
}


def diagnosticar(caminho: Path) -> None:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)

    raw = preservar_arquivo_raw(
        caminho,
        fonte="b3",
        ano=2025,
    )

    total = 0
    menor_data = None
    maior_data = None
    por_ticker = defaultdict(list)

    for cotacao in iterar_cotacoes(caminho):
        total += 1

        if cotacao.data.year != 2025:
            raise RuntimeError(
                f"Registro fora de 2025: {cotacao.ticker} {cotacao.data}"
            )

        if menor_data is None or cotacao.data < menor_data:
            menor_data = cotacao.data
        if maior_data is None or cotacao.data > maior_data:
            maior_data = cotacao.data

        if cotacao.ticker in TICKERS_AUDITORIA:
            por_ticker[cotacao.ticker].append(cotacao.data)

    if total == 0:
        raise RuntimeError("Nenhum registro 01 encontrado no COTAHIST 2025.")

    print("=" * 78)
    print("SISTEMA CVM — PILOTO REAL COTAHIST 2025")
    print("=" * 78)
    print(f"Arquivo: {caminho}")
    print(f"SHA-256: {raw.sha256}")
    print(f"Registros 01: {total:,}")
    print(f"Primeira data: {menor_data}")
    print(f"Última data: {maior_data}")
    print()

    for ticker in sorted(TICKERS_AUDITORIA):
        datas = sorted(set(por_ticker.get(ticker, [])))
        if not datas:
            print(f"{ticker:8s} | ausente no arquivo")
            continue

        print(
            f"{ticker:8s} | primeira={datas[0]} | "
            f"última={datas[-1]} | pregões={len(datas)}"
        )

    erros = []

    natu3 = sorted(set(por_ticker.get("NATU3", [])))
    if not natu3 or natu3[0] != date(2025, 7, 2):
        erros.append(
            "NATU3: primeira ocorrência de 2025 deveria ser 2025-07-02."
        )

    axia3 = sorted(set(por_ticker.get("AXIA3", [])))
    if not axia3 or axia3[0] != date(2025, 11, 10):
        erros.append(
            "AXIA3: primeira ocorrência deveria ser 2025-11-10."
        )

    elet3 = sorted(set(por_ticker.get("ELET3", [])))
    if not elet3:
        erros.append("ELET3: nenhuma ocorrência encontrada em 2025.")
    elif elet3[-1] >= date(2025, 11, 10):
        erros.append(
            "ELET3: há ocorrência em ou após 2025-11-10."
        )

    for ticker in ("PETR3", "PETR4", "TAEE11", "MGLU3"):
        if not por_ticker.get(ticker):
            erros.append(f"{ticker}: nenhuma ocorrência encontrada.")

    print()
    if erros:
        print("RESULTADO: BLOQUEADO")
        for erro in erros:
            print(f"- {erro}")
        raise RuntimeError(
            "Piloto COTAHIST 2025 falhou nas fixtures temporais."
        )

    print("RESULTADO: APROVADO")
    print("Parser validado contra arquivo real de 2025.")
    print("Fixtures temporais críticas reconciliadas com o COTAHIST.")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python tests/mercado/diagnostico_cotahist_2025.py "
            "<caminho_para_COTAHIST_A2025.ZIP>"
        )

    diagnosticar(Path(sys.argv[1]))


if __name__ == "__main__":
    main()

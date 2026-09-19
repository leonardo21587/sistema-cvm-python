from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
    sha256_fca,
)


REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
B3_RESULTADO = REPORTS_DIR / "universo_ampliado_2025_sem_fca_b3.csv"
SAIDA = REPORTS_DIR / "universo_ampliado_2025_pendentes_fca_2024.csv"

STATUS_PENDENTES_B3 = {
    "SEM_CANDIDATO_B3",
    "SEM_DETALHE_B3",
    "TICKER_NAO_ENCONTRADO_NO_GETDETAIL",
}


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
    sistema = _catalogo_sistema()
    resultado_b3 = _ler(B3_RESULTADO)

    pendentes = sorted({
        linha["TICKER"].strip().upper()
        for linha in resultado_b3
        if linha["STATUS"] in STATUS_PENDENTES_B3
    })

    print("=" * 92)
    print("SISTEMA CVM — D.4 — PENDENTES 2025 CONTRA FCA 2024")
    print("=" * 92)
    print(f"Pendentes recebidos da etapa B3: {len(pendentes):,}")

    caminho_fca = baixar_fca(2024)
    registros, ambiguos_cnpj = ler_fca_valores_mobiliarios(
        caminho_fca,
        ano=2024,
    )

    por_ticker: dict[str, list] = {}
    for registro in registros:
        ticker = registro.codigo_negociacao.strip().upper()
        if ticker in pendentes:
            por_ticker.setdefault(ticker, []).append(registro)

    saida = []
    resolvidos = []
    fora_sistema = []
    ambiguos = []
    nao_encontrados = []
    divergencias = []

    for ticker in pendentes:
        grupo = por_ticker.get(ticker, [])

        if not grupo:
            item = {
                "TICKER": ticker,
                "STATUS": "NAO_ENCONTRADO_FCA_2024",
                "CD_CVM": "",
                "CNPJ_FCA": "",
                "DENOM_CIA": "",
                "ISIN_B3": "",
                "DETALHE": "",
            }
            nao_encontrados.append(item)
            saida.append(item)
            continue

        codigos = {
            registro.cd_cvm
            for registro in grupo
            if registro.cd_cvm
        }
        cnpjs = {
            registro.cnpj
            for registro in grupo
            if registro.cnpj
        }

        if len(codigos) != 1:
            item = {
                "TICKER": ticker,
                "STATUS": "AMBIGUO_CD_CVM_FCA_2024",
                "CD_CVM": "|".join(sorted(codigos)),
                "CNPJ_FCA": "|".join(sorted(cnpjs)),
                "DENOM_CIA": "",
                "ISIN_B3": "",
                "DETALHE": f"{len(grupo)} registro(s) FCA",
            }
            ambiguos.append(item)
            saida.append(item)
            continue

        cd_cvm = next(iter(codigos))

        if cd_cvm not in sistema:
            item = {
                "TICKER": ticker,
                "STATUS": "CD_CVM_FCA_2024_FORA_SISTEMA",
                "CD_CVM": cd_cvm,
                "CNPJ_FCA": "|".join(sorted(cnpjs)),
                "DENOM_CIA": "",
                "ISIN_B3": "",
                "DETALHE": f"{len(grupo)} registro(s) FCA",
            }
            fora_sistema.append(item)
            saida.append(item)
            continue

        cnpj_sistema = sistema[cd_cvm]["cnpj"]
        cnpj_confere = (
            not cnpjs
            or cnpjs == {cnpj_sistema}
        )

        if not cnpj_confere:
            item = {
                "TICKER": ticker,
                "STATUS": "CNPJ_DIVERGENTE_FCA_2024",
                "CD_CVM": cd_cvm,
                "CNPJ_FCA": "|".join(sorted(cnpjs)),
                "DENOM_CIA": sistema[cd_cvm]["nome"],
                "ISIN_B3": "",
                "DETALHE": f"CNPJ_SISTEMA={cnpj_sistema}",
            }
            divergencias.append(item)
            saida.append(item)
            continue

        datas_inicio = sorted({
            registro.data_inicio_negociacao.isoformat()
            for registro in grupo
            if registro.data_inicio_negociacao
        })
        datas_fim = sorted({
            registro.data_fim_negociacao.isoformat()
            for registro in grupo
            if registro.data_fim_negociacao
        })
        valores = sorted({
            registro.valor_mobiliario
            for registro in grupo
            if registro.valor_mobiliario
        })

        item = {
            "TICKER": ticker,
            "STATUS": "RESOLVIDO_FCA_2024",
            "CD_CVM": cd_cvm,
            "CNPJ_FCA": (
                next(iter(cnpjs))
                if len(cnpjs) == 1
                else cnpj_sistema
            ),
            "DENOM_CIA": sistema[cd_cvm]["nome"],
            "ISIN_B3": "",
            "DETALHE": (
                f"valor={'|'.join(valores)}; "
                f"inicio={'|'.join(datas_inicio)}; "
                f"fim={'|'.join(datas_fim)}"
            ),
        }
        resolvidos.append(item)
        saida.append(item)

    _escrever(
        SAIDA,
        saida,
        [
            "TICKER",
            "STATUS",
            "CD_CVM",
            "CNPJ_FCA",
            "DENOM_CIA",
            "ISIN_B3",
            "DETALHE",
        ],
    )

    print()
    print("RESUMO")
    print("-" * 92)
    print(f"Resolvidos por FCA 2024: {len(resolvidos):,}")
    print(f"Fora das 499 empresas: {len(fora_sistema):,}")
    print(f"Ambíguos: {len(ambiguos):,}")
    print(f"Divergências de CNPJ: {len(divergencias):,}")
    print(f"Não encontrados no FCA 2024: {len(nao_encontrados):,}")
    print(f"CNPJ ambíguos globais no FCA 2024: {len(ambiguos_cnpj):,}")
    print()

    if resolvidos:
        print("RESOLVIDOS FCA 2024")
        print("-" * 92)
        for item in resolvidos:
            print(
                f"{item['TICKER']:8s} | "
                f"{item['CD_CVM']} | "
                f"{item['DENOM_CIA']}"
            )
        print()

    restantes = (
        fora_sistema
        + ambiguos
        + divergencias
        + nao_encontrados
    )
    if restantes:
        print("AINDA PENDENTES")
        print("-" * 92)
        for item in restantes:
            print(
                f"{item['TICKER']:8s} | "
                f"{item['STATUS']:32s} | "
                f"{item['CD_CVM']:12s} | "
                f"{item['DETALHE']}"
            )
        print()

    print(f"FCA 2024: {caminho_fca}")
    print(f"FCA 2024 SHA-256: {sha256_fca(caminho_fca)}")
    print(f"Relatório: {SAIDA}")
    print()
    print("RESULTADO: DIAGNÓSTICO CONCLUÍDO")
    print(
        "Nenhum CSV oficial de referência e nenhum INSTRUMENTO_ID "
        "foram alterados."
    )


if __name__ == "__main__":
    main()

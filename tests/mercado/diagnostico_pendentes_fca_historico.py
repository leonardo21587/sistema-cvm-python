from __future__ import annotations

import csv
import sys
from collections import defaultdict
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
PENDENTES_2024 = (
    REPORTS_DIR / "universo_ampliado_2025_pendentes_fca_2024.csv"
)
B3_RESULTADO = REPORTS_DIR / "universo_ampliado_2025_sem_fca_b3.csv"
UNIVERSO_2025 = REPORTS_DIR / "universo_ampliado_2025_tickers.csv"
SAIDA = REPORTS_DIR / "universo_ampliado_2025_pendentes_fca_historico.csv"

ANOS = tuple(range(2023, 2009, -1))


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

    pendentes_2024 = _ler(PENDENTES_2024)
    b3 = _ler(B3_RESULTADO)
    universo = _ler(UNIVERSO_2025)

    pendentes = sorted({
        linha["TICKER"].strip().upper()
        for linha in pendentes_2024
        if linha["STATUS"] == "NAO_ENCONTRADO_FCA_2024"
    })

    b3_por_ticker = {
        linha["TICKER"].strip().upper(): linha
        for linha in b3
    }
    universo_por_ticker = {
        linha["TICKER"].strip().upper(): linha
        for linha in universo
    }

    # Tickers já resolvidos em 2025 por CD_CVM, úteis como evidência
    # temporal para casos em que a B3 fornece apenas a companhia candidata.
    resolvidos_por_cd: dict[str, list[dict[str, str]]] = defaultdict(list)
    for linha in universo:
        cd_cvm = linha["CD_CVM"].strip()
        if cd_cvm:
            resolvidos_por_cd[cd_cvm].append(linha)

    print("=" * 96)
    print("SISTEMA CVM — D.4 — PENDENTES 2025 CONTRA FCA HISTÓRICO")
    print("=" * 96)
    print(f"Pendentes recebidos: {len(pendentes):,}")
    print(f"Anos pesquisados: {min(ANOS)}–{max(ANOS)}")
    print()

    encontrados: dict[str, list[tuple[int, object]]] = defaultdict(list)
    anos_ok = []
    erros_ano = []

    for ano in ANOS:
        print(f"FCA {ano}: ", end="", flush=True)
        try:
            caminho = baixar_fca(ano)
            registros, ambiguos = ler_fca_valores_mobiliarios(
                caminho,
                ano=ano,
            )
            anos_ok.append(
                {
                    "ano": ano,
                    "caminho": caminho,
                    "sha256": sha256_fca(caminho),
                    "ambiguos": len(ambiguos),
                }
            )

            achados_ano = 0
            for registro in registros:
                ticker = registro.codigo_negociacao.strip().upper()
                if ticker in pendentes:
                    encontrados[ticker].append((ano, registro))
                    achados_ano += 1

            print(
                f"OK | registros={len(registros):,} | "
                f"matches={achados_ano:,} | "
                f"CNPJ ambíguos={len(ambiguos):,}"
            )
        except Exception as exc:
            erros_ano.append((ano, type(exc).__name__, str(exc)))
            print(f"ERRO | {type(exc).__name__}: {exc}")

    print()

    saida = []
    resolvidos = []
    fora_sistema = []
    ambiguos = []
    nao_encontrados = []

    for ticker in pendentes:
        achados = encontrados.get(ticker, [])
        linha_universo = universo_por_ticker.get(ticker, {})
        linha_b3 = b3_por_ticker.get(ticker, {})

        codigos = {
            registro.cd_cvm
            for _, registro in achados
            if registro.cd_cvm
        }
        cnpjs = {
            registro.cnpj
            for _, registro in achados
            if registro.cnpj
        }
        anos = sorted({ano for ano, _ in achados})

        if not achados:
            status = "NAO_ENCONTRADO_FCA_2010_2023"
            cd_cvm = ""
            detalhe = ""
            nao_encontrados.append(ticker)
        elif len(codigos) != 1:
            status = "AMBIGUO_CD_CVM_FCA_HISTORICO"
            cd_cvm = "|".join(sorted(codigos))
            detalhe = f"anos={','.join(str(x) for x in anos)}"
            ambiguos.append(ticker)
        else:
            cd_cvm = next(iter(codigos))
            if cd_cvm not in sistema:
                status = "CD_CVM_FCA_HISTORICO_FORA_SISTEMA"
                detalhe = f"anos={','.join(str(x) for x in anos)}"
                fora_sistema.append(ticker)
            else:
                cnpj_sistema = sistema[cd_cvm]["cnpj"]
                if cnpjs and cnpjs != {cnpj_sistema}:
                    status = "CNPJ_DIVERGENTE_FCA_HISTORICO"
                    detalhe = (
                        f"CNPJ_FCA={'|'.join(sorted(cnpjs))}; "
                        f"CNPJ_SISTEMA={cnpj_sistema}"
                    )
                    ambiguos.append(ticker)
                else:
                    status = "RESOLVIDO_FCA_HISTORICO"
                    detalhe = f"anos={','.join(str(x) for x in anos)}"
                    resolvidos.append(ticker)

        saida.append(
            {
                "TICKER": ticker,
                "STATUS": status,
                "CD_CVM": cd_cvm,
                "CNPJ_FCA": "|".join(sorted(cnpjs)),
                "ANOS_FCA": "|".join(str(x) for x in anos),
                "TIPO_ATIVO_2025": linha_universo.get("TIPO_ATIVO", ""),
                "CLASSE_2025": linha_universo.get("CLASSE", ""),
                "PRIMEIRA_DATA_2025": linha_universo.get(
                    "PRIMEIRA_DATA_2025", ""
                ),
                "ULTIMA_DATA_2025": linha_universo.get(
                    "ULTIMA_DATA_2025", ""
                ),
                "ISINS_2025": linha_universo.get("ISINS_2025", ""),
                "CD_CVM_CANDIDATO_B3": linha_b3.get("CD_CVM", ""),
                "STATUS_B3": linha_b3.get("STATUS", ""),
                "DETALHE": detalhe,
            }
        )

    _escrever(
        SAIDA,
        saida,
        [
            "TICKER",
            "STATUS",
            "CD_CVM",
            "CNPJ_FCA",
            "ANOS_FCA",
            "TIPO_ATIVO_2025",
            "CLASSE_2025",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
            "ISINS_2025",
            "CD_CVM_CANDIDATO_B3",
            "STATUS_B3",
            "DETALHE",
        ],
    )

    print("RESUMO")
    print("-" * 96)
    print(f"Resolvidos pelo FCA histórico: {len(resolvidos):,}")
    print(f"Fora das 499 empresas: {len(fora_sistema):,}")
    print(f"Ambíguos/divergentes: {len(ambiguos):,}")
    print(f"Não encontrados em 2010–2023: {len(nao_encontrados):,}")
    print(f"Anos FCA processados com sucesso: {len(anos_ok):,}")
    print(f"Anos FCA com erro: {len(erros_ano):,}")
    print()

    if resolvidos:
        print("RESOLVIDOS PELO FCA HISTÓRICO")
        print("-" * 96)
        for item in saida:
            if item["STATUS"] != "RESOLVIDO_FCA_HISTORICO":
                continue
            nome = sistema[item["CD_CVM"]]["nome"]
            print(
                f"{item['TICKER']:8s} | {item['CD_CVM']} | "
                f"{item['ANOS_FCA']:25s} | {nome}"
            )
        print()

    restantes = [
        item
        for item in saida
        if item["STATUS"] != "RESOLVIDO_FCA_HISTORICO"
    ]

    if restantes:
        print("AINDA PENDENTES / FORA DO UNIVERSO")
        print("-" * 96)
        for item in restantes:
            print(
                f"{item['TICKER']:8s} | "
                f"{item['STATUS']:36s} | "
                f"FCA={item['CD_CVM'] or '-':8s} | "
                f"B3={item['CD_CVM_CANDIDATO_B3'] or '-':8s} | "
                f"{item['TIPO_ATIVO_2025']}/{item['CLASSE_2025']} | "
                f"{item['PRIMEIRA_DATA_2025']}→"
                f"{item['ULTIMA_DATA_2025']} | "
                f"ISIN={item['ISINS_2025']}"
            )

            candidato = item["CD_CVM_CANDIDATO_B3"]
            if candidato:
                pares = []
                for linha in sorted(
                    resolvidos_por_cd.get(candidato, []),
                    key=lambda x: (
                        x.get("PRIMEIRA_DATA_2025", ""),
                        x.get("TICKER", ""),
                    ),
                ):
                    pares.append(
                        f"{linha['TICKER']}"
                        f"[{linha['TIPO_ATIVO']}/{linha['CLASSE']}]"
                        f" {linha['PRIMEIRA_DATA_2025']}→"
                        f"{linha['ULTIMA_DATA_2025']}"
                    )
                if pares:
                    print(
                        " " * 11
                        + "tickers 2025 do CD_CVM candidato: "
                        + " | ".join(pares)
                    )
        print()

    if erros_ano:
        print("ERROS POR ANO")
        print("-" * 96)
        for ano, tipo, detalhe in erros_ano:
            print(f"{ano}: {tipo}: {detalhe}")
        print()

    print("ARQUIVOS FCA PROCESSADOS")
    print("-" * 96)
    for item in anos_ok:
        print(
            f"{item['ano']} | SHA-256={item['sha256']} | "
            f"CNPJ ambíguos={item['ambiguos']}"
        )
    print()
    print(f"Relatório: {SAIDA}")
    print()
    print("RESULTADO: DIAGNÓSTICO CONCLUÍDO")
    print(
        "Nenhum CSV oficial de referência e nenhum INSTRUMENTO_ID "
        "foram alterados."
    )


if __name__ == "__main__":
    main()

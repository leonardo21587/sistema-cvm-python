from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
DIAGNOSTICO = REPORTS_DIR / "catalogo_fca_2025_diagnostico.csv"
CANDIDATOS = REPORTS_DIR / "catalogo_instrumentos_candidatos_2025.csv"
REVISAO = REPORTS_DIR / "catalogo_identidade_revisao_2025.csv"


def _bool(valor: str) -> bool:
    return str(valor).strip().lower() in {"true", "1", "sim", "yes"}


def _data(valor: str) -> date | None:
    texto = str(valor or "").strip()
    return date.fromisoformat(texto) if texto else None


def _separar(valor: str) -> set[str]:
    return {
        item.strip().upper()
        for item in str(valor or "").split("|")
        if item.strip()
    }


def _classe_linha(linha: dict[str, str]) -> tuple[str | None, str | None]:
    ticker = linha["TICKER"].strip().upper()
    valor = linha["VALOR_MOBILIARIO"].strip().upper()
    sigla = linha["SIGLA_CLASSE_PREF"].strip().upper()
    composicao = linha["COMPOSICAO_BDR_UNIT"].strip()

    if ticker.endswith("11"):
        if "UNIT" in valor or composicao:
            return "UNIT", "UNIT"
        return None, None

    if ticker.endswith("3"):
        return "ACAO", "ON"

    if ticker[-1:] in {"4", "5", "6", "7", "8"}:
        if sigla in {"PN", "PNA", "PNB", "PNC", "PND"}:
            return "ACAO", sigla

        # FCA pode registrar a classe por extenso sem preencher a sigla.
        classe_extenso = linha["CLASSE_PREF"].strip().upper()
        mapa = {
            "PREFERENCIAL": "PN",
            "PREFERENCIAL CLASSE A": "PNA",
            "PREFERENCIAL CLASSE B": "PNB",
            "PREFERENCIAL CLASSE C": "PNC",
            "PREFERENCIAL CLASSE D": "PND",
        }
        if classe_extenso in mapa:
            return "ACAO", mapa[classe_extenso]

        return None, None

    return None, None


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


def executar() -> None:
    if not DIAGNOSTICO.is_file():
        raise FileNotFoundError(
            "Diagnóstico FCA 2025 não encontrado. Execute primeiro "
            "diagnostico_catalogo_fca_2025.py."
        )

    with DIAGNOSTICO.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        linhas = list(csv.DictReader(arquivo, delimiter=";"))

    validadas = [
        linha
        for linha in linhas
        if linha["STATUS"] == "VALIDADO_COTAHIST_2025"
    ]

    por_ticker: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for linha in validadas:
        por_ticker[(linha["CD_CVM"], linha["TICKER"])].append(linha)

    revisao: list[dict] = []
    ticker_normalizado: list[dict] = []

    for (cd_cvm, ticker), grupo in sorted(por_ticker.items()):
        isins = set()
        especificacoes = set()
        classes = set()
        tipos = set()
        datas_inicio = []
        datas_fim = []

        for linha in grupo:
            isins |= _separar(linha["ISINS_2025"])
            especificacoes |= _separar(linha["ESPECIFICACOES_2025"])

            tipo, classe = _classe_linha(linha)
            if tipo:
                tipos.add(tipo)
            if classe:
                classes.add(classe)

            inicio = _data(linha["PRIMEIRA_DATA_2025"])
            fim = _data(linha["ULTIMA_DATA_2025"])
            if inicio:
                datas_inicio.append(inicio)
            if fim:
                datas_fim.append(fim)

        problemas = []
        if len(isins) == 0:
            problemas.append("SEM_ISIN")
        elif len(isins) > 1:
            problemas.append("MULTIPLOS_ISIN_NO_TICKER")

        if len(tipos) != 1:
            problemas.append("TIPO_ATIVO_NAO_UNICO")
        if len(classes) != 1:
            problemas.append("CLASSE_NAO_UNICA")

        cnpjs = {linha["CNPJ"] for linha in grupo if linha["CNPJ"]}
        if len(cnpjs) != 1:
            problemas.append("CNPJ_NAO_UNICO")

        if not all(_bool(linha["CNPJ_CONFERE"]) for linha in grupo):
            problemas.append("CNPJ_DIVERGENTE")

        if problemas:
            revisao.append(
                {
                    "NIVEL": "TICKER",
                    "CD_CVM": cd_cvm,
                    "TICKER": ticker,
                    "ISIN": "|".join(sorted(isins)),
                    "PROBLEMAS": "|".join(problemas),
                    "QTD_LINHAS_FCA": len(grupo),
                }
            )
            continue

        ticker_normalizado.append(
            {
                "CD_CVM": cd_cvm,
                "CNPJ": next(iter(cnpjs)),
                "DENOM_CIA": grupo[0]["DENOM_SISTEMA"],
                "TICKER": ticker,
                "ISIN": next(iter(isins)),
                "TIPO_ATIVO": next(iter(tipos)),
                "CLASSE": next(iter(classes)),
                "PRIMEIRA_DATA_2025": min(datas_inicio).isoformat(),
                "ULTIMA_DATA_2025": max(datas_fim).isoformat(),
                "PREGOES_2025": max(
                    int(linha["PREGOES_2025"] or 0)
                    for linha in grupo
                ),
                "ESPECIFICACOES_2025": "|".join(
                    sorted(especificacoes)
                ),
                "QTD_LINHAS_FCA": len(grupo),
            }
        )

    # Identidade candidata = companhia + ISIN. O ticker é atributo temporal.
    por_identidade: dict[tuple[str, str], list[dict]] = defaultdict(list)
    isin_cd_cvm: dict[str, set[str]] = defaultdict(set)

    for linha in ticker_normalizado:
        por_identidade[(linha["CD_CVM"], linha["ISIN"])].append(linha)
        isin_cd_cvm[linha["ISIN"]].add(linha["CD_CVM"])

    for isin, codigos in sorted(isin_cd_cvm.items()):
        if len(codigos) > 1:
            revisao.append(
                {
                    "NIVEL": "ISIN",
                    "CD_CVM": "|".join(sorted(codigos)),
                    "TICKER": "",
                    "ISIN": isin,
                    "PROBLEMAS": "ISIN_EM_MULTIPLOS_CD_CVM",
                    "QTD_LINHAS_FCA": "",
                }
            )

    candidatos: list[dict] = []

    for (cd_cvm, isin), grupo in sorted(por_identidade.items()):
        if len(isin_cd_cvm[isin]) > 1:
            continue

        tipos = {linha["TIPO_ATIVO"] for linha in grupo}
        classes = {linha["CLASSE"] for linha in grupo}
        cnpjs = {linha["CNPJ"] for linha in grupo}
        nomes = {linha["DENOM_CIA"] for linha in grupo}
        tickers = sorted({linha["TICKER"] for linha in grupo})

        problemas = []
        if len(tipos) != 1:
            problemas.append("TIPO_ATIVO_DIVERGENTE_NO_ISIN")
        if len(classes) != 1:
            problemas.append("CLASSE_DIVERGENTE_NO_ISIN")
        if len(cnpjs) != 1:
            problemas.append("CNPJ_DIVERGENTE_NO_ISIN")

        intervalos = sorted(
            (
                _data(linha["PRIMEIRA_DATA_2025"]),
                _data(linha["ULTIMA_DATA_2025"]),
                linha["TICKER"],
            )
            for linha in grupo
        )

        sobreposicoes = []
        for indice, atual in enumerate(intervalos):
            for proximo in intervalos[indice + 1:]:
                if (
                    atual[0] is not None
                    and atual[1] is not None
                    and proximo[0] is not None
                    and proximo[1] is not None
                    and atual[0] <= proximo[1]
                    and proximo[0] <= atual[1]
                ):
                    sobreposicoes.append(
                        f"{atual[2]}~{proximo[2]}"
                    )

        if sobreposicoes:
            problemas.append(
                "TICKERS_MESMO_ISIN_COM_SOBREPOSICAO_2025:"
                + ",".join(sobreposicoes)
            )

        if problemas:
            revisao.append(
                {
                    "NIVEL": "INSTRUMENTO",
                    "CD_CVM": cd_cvm,
                    "TICKER": "|".join(tickers),
                    "ISIN": isin,
                    "PROBLEMAS": "|".join(problemas),
                    "QTD_LINHAS_FCA": sum(
                        int(linha["QTD_LINHAS_FCA"])
                        for linha in grupo
                    ),
                }
            )
            continue

        candidatos.append(
            {
                "CHAVE_CANDIDATO": f"{cd_cvm}|{isin}",
                "CD_CVM": cd_cvm,
                "CNPJ": next(iter(cnpjs)),
                "DENOM_CIA": sorted(nomes)[0] if nomes else "",
                "ISIN": isin,
                "TIPO_ATIVO": next(iter(tipos)),
                "CLASSE": next(iter(classes)),
                "TICKERS_2025": "|".join(tickers),
                "QTD_TICKERS_2025": len(tickers),
                "PRIMEIRA_DATA_2025": min(
                    x[0] for x in intervalos if x[0] is not None
                ).isoformat(),
                "ULTIMA_DATA_2025": max(
                    x[1] for x in intervalos if x[1] is not None
                ).isoformat(),
                "PREGOES_SOMA_2025": sum(
                    int(linha["PREGOES_2025"])
                    for linha in grupo
                ),
                "STATUS": "CANDIDATO_VALIDADO_2025",
            }
        )

    _escrever(
        CANDIDATOS,
        candidatos,
        [
            "CHAVE_CANDIDATO",
            "CD_CVM",
            "CNPJ",
            "DENOM_CIA",
            "ISIN",
            "TIPO_ATIVO",
            "CLASSE",
            "TICKERS_2025",
            "QTD_TICKERS_2025",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
            "PREGOES_SOMA_2025",
            "STATUS",
        ],
    )
    _escrever(
        REVISAO,
        revisao,
        [
            "NIVEL",
            "CD_CVM",
            "TICKER",
            "ISIN",
            "PROBLEMAS",
            "QTD_LINHAS_FCA",
        ],
    )

    tickers_multi_fca = sum(
        1 for grupo in por_ticker.values() if len(grupo) > 1
    )
    instrumentos_multi_ticker = sum(
        1 for grupo in por_identidade.values() if len(grupo) > 1
    )

    print("=" * 78)
    print("SISTEMA CVM — D.4 — IDENTIDADE CANDIDATA 2025")
    print("=" * 78)
    print(f"Linhas FCA validadas: {len(validadas):,}")
    print(f"Tickers únicos validados: {len(por_ticker):,}")
    print(
        "Tickers com >1 linha semântica FCA: "
        f"{tickers_multi_fca:,}"
    )
    print(f"Tickers normalizados sem bloqueio: {len(ticker_normalizado):,}")
    print(f"Instrumentos candidatos por CD_CVM+ISIN: {len(por_identidade):,}")
    print(
        "Instrumentos com >1 ticker em 2025: "
        f"{instrumentos_multi_ticker:,}"
    )
    print(f"Instrumentos promovíveis como candidatos: {len(candidatos):,}")
    print(f"Itens para revisão: {len(revisao):,}")
    print()

    multi = [
        linha
        for linha in candidatos
        if int(linha["QTD_TICKERS_2025"]) > 1
    ]
    if multi:
        print("MESMO INSTRUMENTO COM MÚLTIPLOS TICKERS EM 2025")
        print("-" * 78)
        for linha in multi[:20]:
            print(
                f"{linha['CD_CVM']} | {linha['ISIN']} | "
                f"{linha['TICKERS_2025']}"
            )
        print()

    if revisao:
        print("REVISÃO NECESSÁRIA")
        print("-" * 78)
        for linha in revisao[:30]:
            print(
                f"{linha['NIVEL']:11s} | "
                f"{linha['CD_CVM']:12s} | "
                f"{linha['TICKER']:16s} | "
                f"{linha['ISIN']:14s} | "
                f"{linha['PROBLEMAS']}"
            )
        if len(revisao) > 30:
            print(f"... e mais {len(revisao) - 30} item(ns).")
        print()

    print(f"Candidatos: {CANDIDATOS}")
    print(f"Revisão: {REVISAO}")
    print()
    print("RESULTADO: DIAGNÓSTICO CONCLUÍDO")
    print(
        "Nenhum INSTRUMENTO_ID foi criado e os CSVs oficiais do catálogo "
        "permanecem inalterados."
    )


if __name__ == "__main__":
    executar()

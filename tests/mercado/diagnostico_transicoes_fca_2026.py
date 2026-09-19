from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.classificacao import inferir_tipo_classe  # noqa: E402
from src.mercado.providers.b3_cotahist import iterar_cotacoes  # noqa: E402
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
    sha256_fca,
)


REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
DIAGNOSTICO_2025 = REPORTS_DIR / "catalogo_fca_2025_diagnostico.csv"

ALVOS = {"ELET3", "AXIA3", "NATU3", "NTCO3"}


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def _fca_2025_por_ticker() -> dict[str, list[dict[str, str]]]:
    linhas = _ler_csv(DIAGNOSTICO_2025)
    saida: dict[str, list[dict[str, str]]] = defaultdict(list)
    for linha in linhas:
        ticker = str(linha.get("TICKER", "")).strip().upper()
        if ticker in ALVOS:
            saida[ticker].append(linha)
    return saida


def _fca_2026_por_ticker():
    caminho = baixar_fca(2026)
    registros, ambiguos = ler_fca_valores_mobiliarios(
        caminho,
        ano=2026,
    )
    saida = defaultdict(list)
    for registro in registros:
        if registro.codigo_negociacao in ALVOS:
            saida[registro.codigo_negociacao].append(registro)
    return caminho, saida, ambiguos


def _cotahist_2025(caminho: Path):
    saida = defaultdict(
        lambda: {
            "datas": set(),
            "isins": set(),
            "especificacoes": set(),
        }
    )
    for cotacao in iterar_cotacoes(caminho):
        if cotacao.tipo_mercado != "010":
            continue
        if cotacao.ticker not in ALVOS:
            continue
        item = saida[cotacao.ticker]
        item["datas"].add(cotacao.data)
        if cotacao.isin:
            item["isins"].add(cotacao.isin)
        if cotacao.especificacao:
            item["especificacoes"].add(cotacao.especificacao)
    return saida


def _primeiro_valor(grupo, atributo: str):
    for item in grupo:
        valor = getattr(item, atributo)
        if valor:
            return valor
    return None


def executar(cotahist_2025: Path) -> None:
    if not cotahist_2025.is_file():
        raise FileNotFoundError(cotahist_2025)

    fca25 = _fca_2025_por_ticker()
    fca26_path, fca26, ambiguos26 = _fca_2026_por_ticker()
    cot = _cotahist_2025(cotahist_2025)

    print("=" * 94)
    print("SISTEMA CVM — D.4 — TRANSIÇÕES DE IDENTIDADE 2025/2026")
    print("=" * 94)
    print(f"FCA 2026: {fca26_path}")
    print(f"FCA 2026 SHA-256: {sha256_fca(fca26_path)}")
    print(f"CNPJ ambíguos FCA 2026: {len(ambiguos26)}")
    print()

    resumo = {}

    for ticker in sorted(ALVOS):
        antigo = fca25.get(ticker, [])
        novo = fca26.get(ticker, [])
        mercado = cot.get(ticker, {})

        cd25 = {
            str(x.get("CD_CVM", "")).strip()
            for x in antigo
            if str(x.get("CD_CVM", "")).strip()
        }
        cd26 = {
            x.cd_cvm
            for x in novo
            if x.cd_cvm
        }

        datas = sorted(mercado.get("datas", set()))
        isins = sorted(mercado.get("isins", set()))
        especificacoes = sorted(
            mercado.get("especificacoes", set())
        )

        if novo:
            valor = _primeiro_valor(novo, "valor_mobiliario") or ""
            sigla = _primeiro_valor(
                novo,
                "sigla_classe_preferencial",
            ) or ""
            classe = _primeiro_valor(
                novo,
                "classe_preferencial",
            ) or ""
            composicao = _primeiro_valor(
                novo,
                "composicao_bdr_unit",
            ) or ""
        elif antigo:
            valor = antigo[0].get("VALOR_MOBILIARIO", "")
            sigla = antigo[0].get("SIGLA_CLASSE_PREF", "")
            classe = antigo[0].get("CLASSE_PREF", "")
            composicao = antigo[0].get("COMPOSICAO_BDR_UNIT", "")
        else:
            valor = sigla = classe = composicao = ""

        tipo_classe = inferir_tipo_classe(
            ticker=ticker,
            valor_mobiliario=valor,
            sigla_classe_preferencial=sigla,
            classe_preferencial=classe,
            composicao_unit=composicao,
            especificacoes_cotahist="|".join(especificacoes),
        )

        resumo[ticker] = {
            "cd25": cd25,
            "cd26": cd26,
            "datas": datas,
            "isins": isins,
            "tipo_classe": tipo_classe,
        }

        print(f"{ticker}")
        print(f"  CD_CVM no FCA 2025: {sorted(cd25)}")
        print(f"  CD_CVM no FCA 2026: {sorted(cd26)}")
        print(
            "  COTAHIST 2025: "
            + (
                f"{datas[0]}→{datas[-1]} | {len(datas)} pregões"
                if datas
                else "sem ocorrência"
            )
        )
        print(f"  ISIN(s) 2025: {isins}")
        print(f"  especificações B3: {especificacoes}")
        print(f"  tipo/classe inferido: {tipo_classe}")

        if novo:
            for item in novo:
                print(
                    "  FCA 2026: "
                    f"{item.cd_cvm} | "
                    f"{item.valor_mobiliario!r} | "
                    f"início={item.data_inicio_negociacao} | "
                    f"fim={item.data_fim_negociacao}"
                )
        print()

    falhas = []

    elet = resumo["ELET3"]
    axia = resumo["AXIA3"]

    cd_elet = next(iter(elet["cd25"]), None)
    cd_axia = next(iter(axia["cd26"]), None)

    continuidade_elet_axia = (
        cd_elet is not None
        and cd_axia is not None
        and cd_elet == cd_axia
        and elet["tipo_classe"] == axia["tipo_classe"]
        and elet["tipo_classe"] == ("ACAO", "ON")
        and elet["datas"]
        and axia["datas"]
        and max(elet["datas"]) < min(axia["datas"])
    )

    natu = resumo["NATU3"]
    ntco = resumo["NTCO3"]
    cd_natu = (
        next(iter(natu["cd25"]), None)
        or next(iter(natu["cd26"]), None)
    )
    cd_ntco = (
        next(iter(ntco["cd25"]), None)
        or next(iter(ntco["cd26"]), None)
    )

    print("DECISÕES DIAGNÓSTICAS")
    print("-" * 94)
    print(
        "ELET3 → AXIA3 | mesma identidade econômica candidata: "
        f"{continuidade_elet_axia}"
    )
    print(
        "NATU3 vs NTCO3 | CD_CVM distintos: "
        f"{cd_natu!r} vs {cd_ntco!r}"
    )

    if not continuidade_elet_axia:
        falhas.append(
            "ELET3→AXIA3 não satisfez os critérios automáticos de "
            "continuidade."
        )

    if cd_natu and cd_ntco and cd_natu == cd_ntco:
        falhas.append(
            "NATU3 e NTCO3 apareceram com o mesmo CD_CVM, contrariando "
            "a separação observada no diagnóstico anterior."
        )

    print()
    if falhas:
        print("RESULTADO: REVISÃO NECESSÁRIA")
        for falha in falhas:
            print(f"- {falha}")
    else:
        print("RESULTADO: APROVADO")
        print(
            "ELET3→AXIA3 pode compartilhar INSTRUMENTO_ID com ticker/ISIN "
            "temporais."
        )
        print(
            "NATU3 e NTCO3 permanecem instrumentos distintos; eventual "
            "sucessão societária fica para a Fase F."
        )

    print()
    print("Nenhum catálogo oficial ou banco foi alterado.")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python tests/mercado/diagnostico_transicoes_fca_2026.py "
            "<COTAHIST_A2025.ZIP>"
        )
    executar(Path(sys.argv[1]))


if __name__ == "__main__":
    main()

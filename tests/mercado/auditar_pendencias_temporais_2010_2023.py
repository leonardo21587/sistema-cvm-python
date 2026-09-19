from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
)
from src.mercado.reconciliacao_historica import (  # noqa: E402
    ler_csv_semicolon,
    escrever_csv_semicolon,
)


REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"

INVENTARIO = REPORT_ROOT / "inventario_global_2010_2023_nome_fca.csv"
CANDIDATOS = REPORT_ROOT / "candidatos_nome_fca_2010_2023.csv"
REVISOES = REPORT_ROOT / "revisoes_nome_fca_2010_2023.csv"

SAIDA = REPORT_ROOT / "auditoria_pendencias_temporais_2010_2023.csv"
SAIDA_REVISOES = REPORT_ROOT / "auditoria_revisoes_temporais_2010_2023.csv"


def _data(valor: str) -> date | None:
    valor = str(valor or "").strip()
    if not valor:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _sobrepoe(
    inicio_a: date | None,
    fim_a: date | None,
    inicio_b: date,
    fim_b: date,
) -> bool:
    ini = inicio_a or date.min
    fim = fim_a or date.max
    return ini <= fim_b and fim >= inicio_b


def _instrumentos_por_chave() -> dict[tuple[str, str, str], set[str]]:
    caminho = REFERENCE_DIR / "instrumentos.csv"
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    saida: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for linha in linhas:
        chave = (
            linha["CD_CVM"].strip().zfill(6),
            linha["TIPO_ATIVO"].strip().upper(),
            linha["CLASSE"].strip().upper(),
        )
        saida[chave].add(linha["INSTRUMENTO_ID"].strip())
    return saida


def _cds_sistema() -> set[str]:
    con = conectar_cvm(read_only=True)
    try:
        return {
            str(x[0]).strip().zfill(6)
            for x in con.execute("SELECT CD_CVM FROM empresas").fetchall()
        }
    finally:
        con.close()


def main() -> None:
    for caminho in (INVENTARIO, CANDIDATOS, REVISOES):
        if not caminho.is_file():
            raise FileNotFoundError(
                f"Execute primeiro reconciliar_nome_fca_2010_2023.py: {caminho}"
            )

    print("=" * 118)
    print("SISTEMA CVM — D.5 — AUDITORIA TEMPORAL DAS PENDÊNCIAS HISTÓRICAS")
    print("=" * 118)
    print("Somente leitura. Nenhum catálogo, ID ou banco será alterado.")

    inventario = ler_csv_semicolon(INVENTARIO)
    candidatos_nome = ler_csv_semicolon(CANDIDATOS)
    revisoes_nome = ler_csv_semicolon(REVISOES)

    pendentes = [
        x for x in inventario
        if x["STATUS"] == "SEM_EVIDENCIA_SUFICIENTE"
    ]
    tickers_pendentes = sorted({x["TICKER"] for x in pendentes})

    candidatos_por_ticker: dict[str, set[str]] = defaultdict(set)
    for linha in candidatos_nome:
        candidatos_por_ticker[linha["TICKER"]].add(
            linha["CD_CVM"].strip().zfill(6)
        )

    revisoes_tickers = {
        x["TICKER"]
        for x in revisoes_nome
        if x["STATUS"].startswith("REVISAO_")
    }

    print(f"Tickers pendentes únicos: {len(tickers_pendentes):,}")
    print(f"Tickers em revisão nome/FCA: {len(revisoes_tickers):,}")

    print("Carregando FCA 2010–2024...")
    fca_por_ticker: dict[str, list[tuple[int, object]]] = defaultdict(list)

    for ano_fca in range(2010, 2025):
        caminho = baixar_fca(ano_fca)
        registros, _ = ler_fca_valores_mobiliarios(
            caminho,
            ano=ano_fca,
        )
        for registro in registros:
            ticker = registro.codigo_negociacao.strip().upper()
            if ticker in tickers_pendentes:
                fca_por_ticker[ticker].append((ano_fca, registro))

    sistema = _cds_sistema()
    instrumentos = _instrumentos_por_chave()

    saida = []
    resumo_revisoes = []

    for ticker in tickers_pendentes:
        linhas_ticker = [
            x for x in pendentes
            if x["TICKER"] == ticker
        ]

        anos_obs = sorted({int(x["ANO"]) for x in linhas_ticker})
        primeira = min(_data(x["PRIMEIRA_DATA"]) for x in linhas_ticker)
        ultima = max(_data(x["ULTIMA_DATA"]) for x in linhas_ticker)
        tipo = linhas_ticker[0]["TIPO_ATIVO"].strip().upper()
        classe = linhas_ticker[0]["CLASSE"].strip().upper()

        candidatos_nome_cd = candidatos_por_ticker.get(ticker, set())

        exatos_cd: set[str] = set()
        exatos_mesmo_ano_cd: set[str] = set()
        sobrepostos_cd: set[str] = set()
        detalhes_fca = []

        for ano_fca, reg in fca_por_ticker.get(ticker, []):
            cd = reg.cd_cvm.zfill(6) if reg.cd_cvm else ""
            if not cd:
                continue

            exatos_cd.add(cd)
            if ano_fca in anos_obs:
                exatos_mesmo_ano_cd.add(cd)

            ini = reg.data_inicio_negociacao or reg.data_inicio_listagem
            fim = reg.data_fim_negociacao or reg.data_fim_listagem
            if _sobrepoe(ini, fim, primeira, ultima):
                sobrepostos_cd.add(cd)

            detalhes_fca.append(
                "|".join(
                    [
                        str(ano_fca),
                        cd,
                        reg.nome_empresarial.replace("|", "/"),
                        ini.isoformat() if ini else "",
                        fim.isoformat() if fim else "",
                    ]
                )
            )

        candidatos_temporais = set()

        if len(sobrepostos_cd) == 1:
            candidatos_temporais = set(sobrepostos_cd)
            regra_temporal = "FCA_DATA_SOBREPOSICAO_UNICA"
        elif len(exatos_mesmo_ano_cd) == 1:
            candidatos_temporais = set(exatos_mesmo_ano_cd)
            regra_temporal = "FCA_MESMO_ANO_UNICO"
        else:
            regra_temporal = ""

        intersecao_nome_temporal = (
            candidatos_nome_cd & candidatos_temporais
            if candidatos_temporais
            else set()
        )

        if len(intersecao_nome_temporal) == 1:
            cd_sugerido = next(iter(intersecao_nome_temporal))
            status_auditoria = "CANDIDATO_TEMPORAL_FORTE"
        elif (
            not candidatos_nome_cd
            and len(candidatos_temporais) == 1
        ):
            cd_sugerido = next(iter(candidatos_temporais))
            status_auditoria = "CANDIDATO_TEMPORAL_SEM_NOME"
        elif len(candidatos_nome_cd) == 1 and not candidatos_temporais:
            cd_sugerido = next(iter(candidatos_nome_cd))
            status_auditoria = "CANDIDATO_NOME_SEM_CONFIRMACAO_TEMPORAL"
        elif len(candidatos_nome_cd) > 1:
            cd_sugerido = ""
            status_auditoria = "REVISAO_MULTIPLOS_CD_NOME"
        else:
            cd_sugerido = ""
            status_auditoria = "SEM_EVIDENCIA_TEMPORAL"

        ids = set()
        if cd_sugerido:
            ids = instrumentos.get(
                (cd_sugerido, tipo, classe),
                set(),
            )

        if cd_sugerido:
            universo = (
                "SISTEMA"
                if cd_sugerido in sistema
                else "FORA_UNIVERSO"
            )
        else:
            universo = ""

        item = {
            "TICKER": ticker,
            "ANOS_OBSERVADOS": "|".join(str(x) for x in anos_obs),
            "PRIMEIRA_DATA": primeira.isoformat(),
            "ULTIMA_DATA": ultima.isoformat(),
            "TIPO_ATIVO": tipo,
            "CLASSE": classe,
            "CDS_NOME_FCA": "|".join(sorted(candidatos_nome_cd)),
            "CDS_FCA_TICKER_EXATO": "|".join(sorted(exatos_cd)),
            "CDS_FCA_MESMO_ANO": "|".join(sorted(exatos_mesmo_ano_cd)),
            "CDS_FCA_SOBREPOSICAO": "|".join(sorted(sobrepostos_cd)),
            "REGRA_TEMPORAL": regra_temporal,
            "CD_CVM_SUGERIDO": cd_sugerido,
            "UNIVERSO_SUGERIDO": universo,
            "IDS_ATUAIS_MESMA_CHAVE": "|".join(sorted(ids)),
            "STATUS_AUDITORIA": status_auditoria,
            "DETALHES_FCA": " || ".join(sorted(set(detalhes_fca))),
        }
        saida.append(item)

        if ticker in revisoes_tickers:
            resumo_revisoes.append(item)

    escrever_csv_semicolon(SAIDA, saida)
    escrever_csv_semicolon(SAIDA_REVISOES, resumo_revisoes)

    contagens: dict[str, int] = defaultdict(int)
    for item in saida:
        contagens[item["STATUS_AUDITORIA"]] += 1

    print()
    print("RESUMO DA AUDITORIA")
    print("-" * 118)
    for status in sorted(contagens):
        print(f"{status:<46} {contagens[status]:>4}")

    fortes = [
        x for x in saida
        if x["STATUS_AUDITORIA"] in {
            "CANDIDATO_TEMPORAL_FORTE",
            "CANDIDATO_TEMPORAL_SEM_NOME",
        }
    ]

    print()
    print(f"Candidatos temporais fortes/únicos: {len(fortes):,}")
    print(f"Revisões nome/FCA auditadas: {len(resumo_revisoes):,}")

    if fortes:
        print()
        print("CANDIDATOS TEMPORAIS")
        print("-" * 118)
        for item in fortes:
            print(
                f"{item['TICKER']:<10} | "
                f"anos={item['ANOS_OBSERVADOS']:<31} | "
                f"cd={item['CD_CVM_SUGERIDO']} | "
                f"{item['UNIVERSO_SUGERIDO']:<13} | "
                f"{item['REGRA_TEMPORAL']}"
            )

    print()
    print("REVISÕES NOME/FCA — RESULTADO TEMPORAL")
    print("-" * 118)
    for item in resumo_revisoes:
        print(
            f"{item['TICKER']:<10} | "
            f"nome={item['CDS_NOME_FCA']:<35} | "
            f"mesmo_ano={item['CDS_FCA_MESMO_ANO']:<25} | "
            f"sobreposição={item['CDS_FCA_SOBREPOSICAO']:<25} | "
            f"{item['STATUS_AUDITORIA']}"
        )

    print()
    print(f"Relatório completo: {SAIDA}")
    print(f"Relatório das revisões: {SAIDA_REVISOES}")
    print("RESULTADO: AUDITORIA TEMPORAL GERADA")
    print("Nenhum caso foi promovido automaticamente.")


if __name__ == "__main__":
    main()

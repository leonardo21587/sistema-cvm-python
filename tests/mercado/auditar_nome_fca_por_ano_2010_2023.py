from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.providers.cvm_fca import baixar_fca, ler_fca_valores_mobiliarios
from src.mercado.reconciliacao_historica import ler_csv_semicolon, escrever_csv_semicolon
from src.mercado.reconciliacao_nome_fca_historica import candidatos_nome_fca, indexar_companhias_fca

REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
INVENTARIO = REPORT_ROOT / "inventario_global_2010_2023_nome_fca.csv"
SAIDA = REPORT_ROOT / "auditoria_nome_fca_por_ano_2010_2023.csv"


def _diagnosticos():
    saida = {}
    for ano in range(2010, 2024):
        caminho = REPORT_ROOT / str(ano) / f"diagnostico_identidade_{ano}.csv"
        for linha in ler_csv_semicolon(caminho):
            saida[(ano, linha["TICKER"].strip().upper())] = linha
    return saida


def _nomes(linha):
    if not linha:
        return ()
    return tuple(sorted({
        x.strip()
        for x in linha.get("NOMES_RESUMIDOS", "").split("|")
        if x.strip()
    }))


def _candidatos(nomes, indice):
    cds = set()
    regras = set()
    for nome in nomes:
        for cand in candidatos_nome_fca(nome_b3=nome, nomes_por_cd=indice):
            cds.add(cand.cd_cvm)
            regras.add(cand.regra)
    return cds, regras


def main():
    print("=" * 108)
    print("SISTEMA CVM — D.5 — AUDITORIA NOME B3/FCA POR ANO")
    print("=" * 108)
    print("Somente leitura. Nenhum catalogo, ID ou banco sera alterado.")

    inventario = ler_csv_semicolon(INVENTARIO)
    pendentes = [x for x in inventario if x["STATUS"] == "SEM_EVIDENCIA_SUFICIENTE"]
    diag = _diagnosticos()

    print(f"Observacoes pendentes: {len(pendentes):,}")
    print(f"Tickers pendentes unicos: {len({x['TICKER'] for x in pendentes}):,}")

    indice_por_ano = {}
    print("Carregando FCA 2010-2024 por ano...")
    for ano in range(2010, 2025):
        caminho = baixar_fca(ano)
        registros, _ = ler_fca_valores_mobiliarios(caminho, ano=ano)
        indice_por_ano[ano] = indexar_companhias_fca(registros)

    por_ticker = defaultdict(list)

    for linha in pendentes:
        ano = int(linha["ANO"])
        ticker = linha["TICKER"].strip().upper()
        nomes = _nomes(diag.get((ano, ticker)))

        cds_ano, regras_ano = _candidatos(nomes, indice_por_ano.get(ano, {}))

        cds_janela = set()
        regras_janela = set()
        for ano_fca in (ano - 1, ano, ano + 1):
            if ano_fca not in indice_por_ano:
                continue
            cds, regras = _candidatos(nomes, indice_por_ano[ano_fca])
            cds_janela.update(cds)
            regras_janela.update(regras)

        por_ticker[ticker].append({
            "ANO": ano,
            "CDS_ANO": cds_ano,
            "CDS_JANELA": cds_janela,
            "REGRAS_ANO": regras_ano,
            "REGRAS_JANELA": regras_janela,
        })

    resumo = []
    for ticker, itens in sorted(por_ticker.items()):
        unicos_ano = {next(iter(x["CDS_ANO"])) for x in itens if len(x["CDS_ANO"]) == 1}
        unicos_janela = {next(iter(x["CDS_JANELA"])) for x in itens if len(x["CDS_JANELA"]) == 1}
        ambiguos_ano = sum(len(x["CDS_ANO"]) > 1 for x in itens)
        ambiguos_janela = sum(len(x["CDS_JANELA"]) > 1 for x in itens)

        status = "SEM_MATCH_ANUAL"
        cd = ""

        if len(unicos_ano) == 1 and ambiguos_ano == 0:
            cd = next(iter(unicos_ano))
            status = "CANDIDATO_MESMO_ANO_FORTE"
        elif len(unicos_janela) == 1 and ambiguos_janela == 0:
            cd = next(iter(unicos_janela))
            status = "CANDIDATO_JANELA_1_FORTE"
        else:
            todos = set()
            for x in itens:
                todos.update(x["CDS_ANO"])
                todos.update(x["CDS_JANELA"])
            if len(todos) > 1:
                status = "REVISAO_MULTIPLOS_CD_ANUAL"

        resumo.append({
            "TICKER": ticker,
            "ANOS": "|".join(str(x["ANO"]) for x in sorted(itens, key=lambda z: z["ANO"])),
            "STATUS_AUDITORIA": status,
            "CD_CVM_SUGERIDO": cd,
            "CDS_UNICOS_MESMO_ANO": "|".join(sorted(unicos_ano)),
            "CDS_UNICOS_JANELA_1": "|".join(sorted(unicos_janela)),
            "OBS_AMBIGUAS_MESMO_ANO": str(ambiguos_ano),
            "OBS_AMBIGUAS_JANELA_1": str(ambiguos_janela),
        })

    escrever_csv_semicolon(SAIDA, resumo)
    contagem = Counter(x["STATUS_AUDITORIA"] for x in resumo)

    print()
    print("RESUMO")
    print("-" * 108)
    for status in sorted(contagem):
        print(f"{status:<42} {contagem[status]:>4}")

    candidatos = [x for x in resumo if x["STATUS_AUDITORIA"].startswith("CANDIDATO_")]
    print()
    print(f"Candidatos anuais fortes: {len(candidatos):,}")

    if candidatos:
        print()
        print("CANDIDATOS ANUAIS FORTES")
        print("-" * 108)
        for item in candidatos:
            print(f"{item['TICKER']:<10} | anos={item['ANOS']:<31} | cd={item['CD_CVM_SUGERIDO']} | {item['STATUS_AUDITORIA']}")

    revisoes = [x for x in resumo if x["STATUS_AUDITORIA"] == "REVISAO_MULTIPLOS_CD_ANUAL"]
    if revisoes:
        print()
        print("REVISOES ANUAIS")
        print("-" * 108)
        for item in revisoes:
            print(f"{item['TICKER']:<10} | mesmo_ano={item['CDS_UNICOS_MESMO_ANO']:<30} | janela={item['CDS_UNICOS_JANELA_1']:<30}")

    print()
    print(f"Relatorio: {SAIDA}")
    print("RESULTADO: AUDITORIA ANUAL NOME/FCA GERADA")
    print("Nenhum caso foi promovido automaticamente.")


if __name__ == "__main__":
    main()

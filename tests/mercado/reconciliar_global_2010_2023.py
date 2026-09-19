from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.reconciliacao_historica import (  # noqa: E402
    ler_csv_semicolon,
    reconciliar_diagnostico,
    serializar_resultados,
    escrever_csv_semicolon,
)
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
)


ANOS = tuple(range(2010, 2024))
ANOS_FCA = tuple(range(2010, 2025))

REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
REPORT_ROOT = ROOT_DIR / "data" / "market" / "reports" / "d5_historico"
EXCECOES = REFERENCE_DIR / "vinculos_validados_2025.csv"

SAIDA_GLOBAL = REPORT_ROOT / "inventario_global_2010_2023.csv"
SAIDA_NOVOS = REPORT_ROOT / "candidatos_instrumentos_historicos_2010_2023.csv"
SAIDA_ALIASES = REPORT_ROOT / "aliases_historicos_2010_2023.csv"
SAIDA_PENDENCIAS = REPORT_ROOT / "pendencias_historicas_2010_2023.csv"


def _ler_instrumentos() -> list[dict[str, str]]:
    with (REFERENCE_DIR / "instrumentos.csv").open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        return list(csv.DictReader(arquivo))


def _normalizar_cnpj(valor: object) -> str:
    digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
    return digitos.zfill(14) if digitos else ""


def _mapas_sistema() -> tuple[set[str], dict[str, str]]:
    con = conectar_cvm(read_only=True)
    try:
        linhas = con.execute(
            """
            SELECT CD_CVM, CNPJ_CIA
            FROM empresas
            ORDER BY CD_CVM
            """
        ).fetchall()
    finally:
        con.close()

    cds = set()
    candidatos_cnpj: dict[str, set[str]] = {}

    for cd_cvm, cnpj in linhas:
        cd = str(cd_cvm).strip().zfill(6)
        cds.add(cd)

        chave = _normalizar_cnpj(cnpj)
        if chave:
            candidatos_cnpj.setdefault(chave, set()).add(cd)

    por_cnpj = {
        cnpj: next(iter(codigos))
        for cnpj, codigos in candidatos_cnpj.items()
        if len(codigos) == 1
    }
    return cds, por_cnpj


def _agregar_novos(linhas: list[dict[str, str]]) -> list[dict[str, str]]:
    grupos: dict[str, dict[str, object]] = {}

    for linha in linhas:
        if linha["STATUS"] != "NOVO_INSTRUMENTO_HISTORICO_CANDIDATO":
            continue

        chave = linha["CHAVE_INSTRUMENTO"]
        g = grupos.setdefault(
            chave,
            {
                "CHAVE_INSTRUMENTO": chave,
                "CD_CVM": linha["CD_CVM"],
                "TIPO_ATIVO": linha["TIPO_ATIVO"],
                "CLASSE": linha["CLASSE"],
                "tickers": set(),
                "anos": set(),
                "primeira": linha["PRIMEIRA_DATA"],
                "ultima": linha["ULTIMA_DATA"],
                "fontes": set(),
            },
        )
        g["tickers"].add(linha["TICKER"])
        g["anos"].add(int(linha["ANO"]))
        g["primeira"] = min(g["primeira"], linha["PRIMEIRA_DATA"])
        g["ultima"] = max(g["ultima"], linha["ULTIMA_DATA"])
        if linha["FONTE"]:
            g["fontes"].add(linha["FONTE"])

    return [
        {
            "CHAVE_INSTRUMENTO": g["CHAVE_INSTRUMENTO"],
            "CD_CVM": g["CD_CVM"],
            "TIPO_ATIVO": g["TIPO_ATIVO"],
            "CLASSE": g["CLASSE"],
            "TICKERS": "|".join(sorted(g["tickers"])),
            "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
            "PRIMEIRA_DATA_OBSERVADA": g["primeira"],
            "ULTIMA_DATA_OBSERVADA": g["ultima"],
            "FONTES": "|".join(sorted(g["fontes"])),
            "STATUS": "CANDIDATO_GLOBAL_SEM_ID",
        }
        for _, g in sorted(grupos.items())
    ]


def _agregar_aliases(linhas: list[dict[str, str]]) -> list[dict[str, str]]:
    grupos: dict[tuple[str, str], dict[str, object]] = {}

    for linha in linhas:
        if linha["STATUS"] != "ALIAS_EXISTENTE_FORTE":
            continue

        chave = (linha["INSTRUMENTO_ID"], linha["TICKER"])
        g = grupos.setdefault(
            chave,
            {
                "INSTRUMENTO_ID": linha["INSTRUMENTO_ID"],
                "TICKER": linha["TICKER"],
                "CD_CVM": linha["CD_CVM"],
                "TIPO_ATIVO": linha["TIPO_ATIVO"],
                "CLASSE": linha["CLASSE"],
                "anos": set(),
                "primeira": linha["PRIMEIRA_DATA"],
                "ultima": linha["ULTIMA_DATA"],
                "fontes": set(),
            },
        )
        g["anos"].add(int(linha["ANO"]))
        g["primeira"] = min(g["primeira"], linha["PRIMEIRA_DATA"])
        g["ultima"] = max(g["ultima"], linha["ULTIMA_DATA"])
        if linha["FONTE"]:
            g["fontes"].add(linha["FONTE"])

    return [
        {
            "INSTRUMENTO_ID": g["INSTRUMENTO_ID"],
            "TICKER": g["TICKER"],
            "CD_CVM": g["CD_CVM"],
            "TIPO_ATIVO": g["TIPO_ATIVO"],
            "CLASSE": g["CLASSE"],
            "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
            "PRIMEIRA_DATA_OBSERVADA": g["primeira"],
            "ULTIMA_DATA_OBSERVADA": g["ultima"],
            "FONTES": "|".join(sorted(g["fontes"])),
            "STATUS": "ALIAS_GLOBAL_CANDIDATO",
        }
        for _, g in sorted(grupos.items())
    ]


def _agregar_pendencias(linhas: list[dict[str, str]]) -> list[dict[str, str]]:
    grupos: dict[tuple[str, str], dict[str, object]] = {}

    for linha in linhas:
        status = linha["STATUS"]
        if not (
            status.startswith("REVISAO_")
            or status == "SEM_EVIDENCIA_SUFICIENTE"
        ):
            continue

        chave = (linha["TICKER"], status)
        g = grupos.setdefault(
            chave,
            {
                "TICKER": linha["TICKER"],
                "STATUS": status,
                "anos": set(),
                "cds": set(),
                "detalhes": set(),
            },
        )
        g["anos"].add(int(linha["ANO"]))
        if linha["CD_CVM"]:
            g["cds"].add(linha["CD_CVM"])
        if linha["DETALHE"]:
            g["detalhes"].add(linha["DETALHE"])

    return [
        {
            "TICKER": g["TICKER"],
            "STATUS": g["STATUS"],
            "ANOS": "|".join(str(x) for x in sorted(g["anos"])),
            "CD_CVM": "|".join(sorted(g["cds"])),
            "DETALHES": " || ".join(sorted(g["detalhes"])),
        }
        for _, g in sorted(grupos.items())
    ]


def main() -> None:
    print("=" * 108)
    print("SISTEMA CVM — D.5 — RECONCILIAÇÃO GLOBAL SOBRE DIAGNÓSTICOS EXISTENTES")
    print("=" * 108)
    print("COTAHIST não será relido. Nenhum catálogo ou banco será alterado.")

    instrumentos = _ler_instrumentos()
    excecoes = ler_csv_semicolon(EXCECOES)
    cd_cvm_sistema, cnpj_para_cd = _mapas_sistema()

    print()
    print(f"Empresas no sistema: {len(cd_cvm_sistema):,}")
    print(f"CNPJ únicos utilizáveis como ponte: {len(cnpj_para_cd):,}")

    print()
    print("Carregando FCA 2010–2024...")
    fca_por_ano = {}
    for ano in ANOS_FCA:
        caminho = baixar_fca(ano)
        registros, ambiguos = ler_fca_valores_mobiliarios(
            caminho,
            ano=ano,
        )
        fca_por_ano[ano] = registros
        print(
            f"FCA {ano}: {len(registros):>5,} registros | "
            f"CNPJ ambíguos: {len(ambiguos)}"
        )

    global_linhas: list[dict[str, str]] = []

    for ano in reversed(ANOS):
        diag_path = (
            REPORT_ROOT
            / str(ano)
            / f"diagnostico_identidade_{ano}.csv"
        )
        if not diag_path.is_file():
            raise FileNotFoundError(
                f"Diagnóstico anual ausente: {diag_path}"
            )

        diagnostico = ler_csv_semicolon(diag_path)
        reconciliados = reconciliar_diagnostico(
            diagnostico=diagnostico,
            instrumentos=instrumentos,
            registros_fca_por_ano=fca_por_ano,
            cd_cvm_sistema=cd_cvm_sistema,
            excecoes_validadas=excecoes,
            cnpj_sistema_para_cd_cvm=cnpj_para_cd,
        )
        serializados = serializar_resultados(reconciliados)

        diag_por_ticker = {
            x["TICKER"]: x
            for x in diagnostico
        }
        linhas_ano = []

        for linha in serializados:
            diag = diag_por_ticker[linha["TICKER"]]
            item = {
                "ANO": str(ano),
                "PRIMEIRA_DATA": diag["PRIMEIRA_DATA"],
                "ULTIMA_DATA": diag["ULTIMA_DATA"],
                **linha,
            }
            linhas_ano.append(item)
            global_linhas.append(item)

        rec_path = (
            REPORT_ROOT
            / str(ano)
            / f"reconciliacao_identidade_{ano}.csv"
        )
        escrever_csv_semicolon(rec_path, linhas_ano)

        c = Counter(x["STATUS"] for x in linhas_ano)
        revisoes = sum(
            qtd
            for status, qtd in c.items()
            if status.startswith("REVISAO_")
        )
        print(
            f"{ano}: total={len(linhas_ano):>3} | "
            f"resolvidos={c['RESOLVIDO_EXISTENTE']:>3} | "
            f"aliases={c['ALIAS_EXISTENTE_FORTE']:>3} | "
            f"novos={c['NOVO_INSTRUMENTO_HISTORICO_CANDIDATO']:>3} | "
            f"fora={c['FORA_UNIVERSO_SISTEMA']:>3} | "
            f"revisões={revisoes:>3} | "
            f"sem={c['SEM_EVIDENCIA_SUFICIENTE']:>3}"
        )

    escrever_csv_semicolon(SAIDA_GLOBAL, global_linhas)

    novos = _agregar_novos(global_linhas)
    aliases = _agregar_aliases(global_linhas)
    pendencias = _agregar_pendencias(global_linhas)

    escrever_csv_semicolon(SAIDA_NOVOS, novos)
    escrever_csv_semicolon(SAIDA_ALIASES, aliases)
    escrever_csv_semicolon(SAIDA_PENDENCIAS, pendencias)

    c = Counter(x["STATUS"] for x in global_linhas)
    revisoes = sum(
        qtd
        for status, qtd in c.items()
        if status.startswith("REVISAO_")
    )

    print()
    print("=" * 108)
    print("RESUMO GLOBAL RECONCILIADO 2010–2023")
    print("=" * 108)
    print(f"Observações ticker-ano: {len(global_linhas):,}")
    print(f"Tickers únicos observados: {len({x['TICKER'] for x in global_linhas}):,}")
    print(f"Já resolvidos pelo catálogo: {c['RESOLVIDO_EXISTENTE']:,}")
    print(f"Alias ticker-ano com evidência forte: {c['ALIAS_EXISTENTE_FORTE']:,}")
    print(f"Aliases históricos únicos candidatos: {len(aliases):,}")
    print(
        "Ocorrências de novos instrumentos históricos: "
        f"{c['NOVO_INSTRUMENTO_HISTORICO_CANDIDATO']:,}"
    )
    print(f"Grupos históricos novos únicos: {len(novos):,}")
    print(f"Fora do universo contábil: {c['FORA_UNIVERSO_SISTEMA']:,}")
    print(f"Revisões necessárias: {revisoes:,}")
    print(f"Sem evidência suficiente: {c['SEM_EVIDENCIA_SUFICIENTE']:,}")
    print(f"Pendências únicas: {len(pendencias):,}")

    if pendencias:
        print()
        print("PENDÊNCIAS ÚNICAS")
        print("-" * 108)
        for item in pendencias:
            print(
                f"{item['TICKER']:<12} | "
                f"{item['STATUS']:<38} | "
                f"anos={item['ANOS']:<35} | "
                f"{item['CD_CVM']}"
            )

    print()
    print("RESULTADO: RECONCILIAÇÃO GLOBAL GERADA")
    print("Não promover nem alocar IDs ainda.")


if __name__ == "__main__":
    main()

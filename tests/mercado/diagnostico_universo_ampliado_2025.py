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
    sha256_fca,
)
from src.mercado.universo import (  # noqa: E402
    indexar_fca_por_ticker,
    intervalos_ticker_sobrepostos,
    resolver_vinculo_fca,
    resumir_cotahist_ano,
)


REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"


def _digitos(valor: object) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def _data(valor: str) -> date | None:
    valor = str(valor or "").strip()
    return date.fromisoformat(valor) if valor else None


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


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


def _referencia_existente():
    instrumentos = _ler_csv(REFERENCE_DIR / "instrumentos.csv")
    tickers = _ler_csv(REFERENCE_DIR / "tickers_historico.csv")

    instrumento_por_id = {
        int(linha["INSTRUMENTO_ID"]): linha
        for linha in instrumentos
    }

    por_ticker = defaultdict(list)
    for linha in tickers:
        por_ticker[linha["TICKER"].strip().upper()].append(linha)

    return instrumento_por_id, por_ticker


def _ids_existentes_no_intervalo(
    *,
    ticker: str,
    inicio: date,
    fim: date,
    referencia_por_ticker,
) -> set[int]:
    ids = set()

    for linha in referencia_por_ticker.get(ticker, []):
        inicio_ref = _data(linha["DT_INICIO"])
        fim_ref = _data(linha["DT_FIM"])

        # Intervalo de referência é semiaberto [inicio, fim).
        if inicio_ref is not None and fim < inicio_ref:
            continue
        if fim_ref is not None and inicio >= fim_ref:
            continue

        ids.add(int(linha["INSTRUMENTO_ID"]))

    return ids


def executar(cotahist_2025: Path) -> None:
    if not cotahist_2025.is_file():
        raise FileNotFoundError(cotahist_2025)

    sistema = _catalogo_sistema()
    instrumento_por_id, referencia_por_ticker = _referencia_existente()

    fca_paths = {
        2025: baixar_fca(2025),
        2026: baixar_fca(2026),
    }
    registros_por_ano = {}
    ambiguidades_fca = {}

    for ano, caminho in fca_paths.items():
        registros, ambiguos = ler_fca_valores_mobiliarios(
            caminho,
            ano=ano,
        )
        registros_por_ano[ano] = registros
        ambiguidades_fca[ano] = ambiguos

    indice_fca = indexar_fca_por_ticker(registros_por_ano)
    resumos = resumir_cotahist_ano(
        cotahist_2025,
        ano=2025,
    )

    linhas_ticker = []
    revisao = []
    prontos = []

    for ticker, resumo in sorted(resumos.items()):
        vinculo = resolver_vinculo_fca(ticker, indice_fca)

        cd_cvm = vinculo.cd_cvm or ""
        dados_sistema = sistema.get(cd_cvm)
        no_sistema = dados_sistema is not None

        cnpj_confere = bool(
            dados_sistema
            and vinculo.cnpj
            and dados_sistema["cnpj"] == vinculo.cnpj
        )

        status = ""
        motivo = ""

        if vinculo.status != "RESOLVIDO":
            status = "REVISAO"
            motivo = vinculo.status
        elif not no_sistema:
            status = "FORA_UNIVERSO_SISTEMA"
        elif not cnpj_confere:
            status = "REVISAO"
            motivo = "CNPJ_DIVERGENTE_SISTEMA"
        else:
            status = "PRONTO_PARA_AGRUPAR"

        ids_existentes = _ids_existentes_no_intervalo(
            ticker=ticker,
            inicio=resumo.primeira_data,
            fim=resumo.ultima_data,
            referencia_por_ticker=referencia_por_ticker,
        )

        linha = {
            "TICKER": ticker,
            "CD_CVM": cd_cvm,
            "CNPJ_FCA": vinculo.cnpj or "",
            "DENOM_CIA": (
                dados_sistema["nome"] if dados_sistema else ""
            ),
            "TIPO_ATIVO": resumo.tipo_ativo,
            "CLASSE": resumo.classe,
            "PRIMEIRA_DATA_2025": resumo.primeira_data.isoformat(),
            "ULTIMA_DATA_2025": resumo.ultima_data.isoformat(),
            "PREGOES_2025": resumo.pregoes,
            "ISINS_2025": "|".join(resumo.isins),
            "ESPECIFICACOES_2025": "|".join(resumo.especificacoes),
            "ANOS_FCA": "|".join(str(x) for x in vinculo.anos_fca),
            "QTD_REGISTROS_FCA": vinculo.quantidade_registros,
            "INSTRUMENTO_ID_EXISTENTE": "|".join(
                str(x) for x in sorted(ids_existentes)
            ),
            "STATUS": status,
            "MOTIVO": motivo,
        }
        linhas_ticker.append(linha)

        if status == "PRONTO_PARA_AGRUPAR":
            prontos.append((resumo, vinculo, ids_existentes))
        elif status == "REVISAO":
            revisao.append(
                {
                    "NIVEL": "TICKER",
                    "CHAVE": ticker,
                    "CD_CVM": cd_cvm,
                    "DETALHE": motivo,
                }
            )

    por_grupo = defaultdict(list)
    for resumo, vinculo, ids_existentes in prontos:
        chave = (
            vinculo.cd_cvm,
            resumo.tipo_ativo,
            resumo.classe,
        )
        por_grupo[chave].append(
            (resumo, vinculo, ids_existentes)
        )

    grupos = []

    for (cd_cvm, tipo, classe), itens in sorted(por_grupo.items()):
        resumos_grupo = [item[0] for item in itens]
        tickers = sorted({item.ticker for item in resumos_grupo})
        isins = sorted({
            isin
            for item in resumos_grupo
            for isin in item.isins
        })
        ids_existentes = set().union(
            *(item[2] for item in itens)
        )

        conflitos = intervalos_ticker_sobrepostos(
            resumos_grupo
        )

        problemas = []

        if conflitos:
            problemas.append(
                "TICKERS_COM_SOBREPOSICAO:"
                + ",".join(f"{a}~{b}" for a, b in conflitos)
            )

        if len(ids_existentes) > 1:
            problemas.append(
                "MULTIPLOS_INSTRUMENTO_ID_EXISTENTES:"
                + ",".join(str(x) for x in sorted(ids_existentes))
            )

        if len(ids_existentes) == 1:
            instrumento_id = next(iter(ids_existentes))
            existente = instrumento_por_id.get(instrumento_id)

            if existente is None:
                problemas.append(
                    "INSTRUMENTO_ID_REFERENCIADO_NAO_EXISTE"
                )
            else:
                if existente["CD_CVM"].strip().zfill(6) != cd_cvm:
                    problemas.append("CD_CVM_DIVERGENTE_REFERENCIA")
                if existente["TIPO_ATIVO"].strip().upper() != tipo:
                    problemas.append("TIPO_DIVERGENTE_REFERENCIA")
                if existente["CLASSE"].strip().upper() != classe:
                    problemas.append("CLASSE_DIVERGENTE_REFERENCIA")

        status = "REVISAO" if problemas else "CANDIDATO_APROVADO"

        primeira = min(
            item.primeira_data for item in resumos_grupo
        )
        ultima = max(
            item.ultima_data for item in resumos_grupo
        )

        grupos.append(
            {
                "CHAVE_CANDIDATO": f"{cd_cvm}|{tipo}|{classe}",
                "CD_CVM": cd_cvm,
                "CNPJ": itens[0][1].cnpj or "",
                "DENOM_CIA": sistema[cd_cvm]["nome"],
                "TIPO_ATIVO": tipo,
                "CLASSE": classe,
                "TICKERS_2025": "|".join(tickers),
                "QTD_TICKERS_2025": len(tickers),
                "ISINS_2025": "|".join(isins),
                "QTD_ISINS_2025": len(isins),
                "PRIMEIRA_DATA_2025": primeira.isoformat(),
                "ULTIMA_DATA_2025": ultima.isoformat(),
                "INSTRUMENTO_ID_EXISTENTE": (
                    str(next(iter(ids_existentes)))
                    if len(ids_existentes) == 1
                    else ""
                ),
                "STATUS": status,
                "PROBLEMAS": "|".join(problemas),
            }
        )

        if problemas:
            revisao.append(
                {
                    "NIVEL": "GRUPO",
                    "CHAVE": f"{cd_cvm}|{tipo}|{classe}",
                    "CD_CVM": cd_cvm,
                    "DETALHE": "|".join(problemas),
                }
            )

    caminho_tickers = (
        REPORTS_DIR / "universo_ampliado_2025_tickers.csv"
    )
    caminho_grupos = (
        REPORTS_DIR / "universo_ampliado_2025_grupos.csv"
    )
    caminho_revisao = (
        REPORTS_DIR / "universo_ampliado_2025_revisao.csv"
    )

    _escrever(
        caminho_tickers,
        linhas_ticker,
        [
            "TICKER",
            "CD_CVM",
            "CNPJ_FCA",
            "DENOM_CIA",
            "TIPO_ATIVO",
            "CLASSE",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
            "PREGOES_2025",
            "ISINS_2025",
            "ESPECIFICACOES_2025",
            "ANOS_FCA",
            "QTD_REGISTROS_FCA",
            "INSTRUMENTO_ID_EXISTENTE",
            "STATUS",
            "MOTIVO",
        ],
    )
    _escrever(
        caminho_grupos,
        grupos,
        [
            "CHAVE_CANDIDATO",
            "CD_CVM",
            "CNPJ",
            "DENOM_CIA",
            "TIPO_ATIVO",
            "CLASSE",
            "TICKERS_2025",
            "QTD_TICKERS_2025",
            "ISINS_2025",
            "QTD_ISINS_2025",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
            "INSTRUMENTO_ID_EXISTENTE",
            "STATUS",
            "PROBLEMAS",
        ],
    )
    _escrever(
        caminho_revisao,
        revisao,
        ["NIVEL", "CHAVE", "CD_CVM", "DETALHE"],
    )

    tickers_no_sistema = sum(
        1
        for linha in linhas_ticker
        if linha["CD_CVM"]
        and linha["CD_CVM"] in sistema
    )
    fora = sum(
        1
        for linha in linhas_ticker
        if linha["STATUS"] == "FORA_UNIVERSO_SISTEMA"
    )
    grupos_aprovados = sum(
        1 for linha in grupos
        if linha["STATUS"] == "CANDIDATO_APROVADO"
    )
    grupos_multi_ticker = [
        linha for linha in grupos
        if int(linha["QTD_TICKERS_2025"]) > 1
    ]

    print("=" * 88)
    print("SISTEMA CVM — D.4 — UNIVERSO AMPLIADO 2025")
    print("=" * 88)
    print(f"Ações/Units observadas no COTAHIST 2025: {len(resumos):,}")
    print(
        "Tickers com CD_CVM efetivamente ligado às 499 empresas: "
        f"{tickers_no_sistema:,}"
    )
    print(f"Tickers fora do universo do sistema: {fora:,}")
    print(f"Grupos econômicos candidatos: {len(grupos):,}")
    print(f"Grupos candidatos aprovados: {grupos_aprovados:,}")
    print(f"Itens de revisão: {len(revisao):,}")
    print(
        "CNPJ ambíguos FCA 2025/2026: "
        f"{sum(len(x) for x in ambiguidades_fca.values()):,}"
    )
    print()

    if grupos_multi_ticker:
        print("GRUPOS COM MÚLTIPLOS TICKERS EM 2025")
        print("-" * 88)
        for linha in grupos_multi_ticker[:30]:
            print(
                f"{linha['CD_CVM']} | "
                f"{linha['TIPO_ATIVO']}/{linha['CLASSE']} | "
                f"{linha['TICKERS_2025']} | "
                f"IDs existentes={linha['INSTRUMENTO_ID_EXISTENTE'] or '-'} | "
                f"{linha['STATUS']}"
            )
        print()

    if revisao:
        print("REVISÃO")
        print("-" * 88)
        for item in revisao[:40]:
            print(
                f"{item['NIVEL']:6s} | "
                f"{item['CHAVE']:24s} | "
                f"{item['CD_CVM']:6s} | "
                f"{item['DETALHE']}"
            )
        if len(revisao) > 40:
            print(f"... e mais {len(revisao) - 40} item(ns).")
        print()

    print(f"FCA 2025 SHA-256: {sha256_fca(fca_paths[2025])}")
    print(f"FCA 2026 SHA-256: {sha256_fca(fca_paths[2026])}")
    print(f"Tickers: {caminho_tickers}")
    print(f"Grupos: {caminho_grupos}")
    print(f"Revisão: {caminho_revisao}")
    print()
    print("RESULTADO: DIAGNÓSTICO CONCLUÍDO")
    print(
        "Nenhum novo INSTRUMENTO_ID foi atribuído e nenhum CSV oficial "
        "de referência foi alterado."
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python tests/mercado/diagnostico_universo_ampliado_2025.py "
            "<COTAHIST_A2025.ZIP>"
        )

    executar(Path(sys.argv[1]))


if __name__ == "__main__":
    main()

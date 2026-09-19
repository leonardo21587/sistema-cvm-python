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
from src.mercado.reconciliacao_catalogo import (  # noqa: E402
    EvidenciaVinculo,
    resolver_evidencias,
)


REPORTS = ROOT_DIR / "data" / "market" / "reports"
REFERENCIA = ROOT_DIR / "data" / "reference" / "mercado"

UNIVERSO = REPORTS / "universo_ampliado_2025_tickers.csv"
B3 = REPORTS / "universo_ampliado_2025_sem_fca_b3.csv"
FCA24 = REPORTS / "universo_ampliado_2025_pendentes_fca_2024.csv"
FCAHIST = REPORTS / "universo_ampliado_2025_pendentes_fca_historico.csv"
EXCECOES = REFERENCIA / "vinculos_validados_2025.csv"

SAIDA_TICKERS = REPORTS / "universo_2025_reconciliado_tickers.csv"
SAIDA_GRUPOS = REPORTS / "universo_2025_reconciliado_grupos.csv"
SAIDA_REVISAO = REPORTS / "universo_2025_reconciliado_revisao.csv"


def _ler(caminho: Path, delimitador: str = ";") -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=delimitador))


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

    def digitos(valor: object) -> str:
        return "".join(ch for ch in str(valor or "") if ch.isdigit())

    return {
        str(cd_cvm).strip().zfill(6): {
            "cnpj": digitos(cnpj).zfill(14),
            "nome": str(nome or "").strip(),
        }
        for cd_cvm, cnpj, nome in linhas
    }


def _data(valor: str) -> date:
    return date.fromisoformat(valor)


def _adicionar(
    destino: dict[str, list[EvidenciaVinculo]],
    *,
    ticker: str,
    cd_cvm: str,
    status: str,
    fonte: str,
    prioridade: int,
) -> None:
    ticker = ticker.strip().upper()
    if not ticker:
        return
    destino[ticker].append(
        EvidenciaVinculo(
            ticker=ticker,
            cd_cvm=cd_cvm.strip().zfill(6) if cd_cvm.strip() else None,
            status=status,
            fonte=fonte,
            prioridade=prioridade,
        )
    )


def main() -> None:
    sistema = _catalogo_sistema()
    universo = _ler(UNIVERSO)
    b3 = _ler(B3)
    fca24 = _ler(FCA24)
    fcahist = _ler(FCAHIST)
    excecoes = _ler(EXCECOES)

    evidencias: dict[str, list[EvidenciaVinculo]] = defaultdict(list)

    # 1. FCA 2025/2026 já reconciliado com o COTAHIST.
    for linha in universo:
        ticker = linha["TICKER"]
        status = linha["STATUS"]
        if status == "PRONTO_PARA_AGRUPAR":
            _adicionar(
                evidencias,
                ticker=ticker,
                cd_cvm=linha["CD_CVM"],
                status="RESOLVIDO_FCA_2025_2026",
                fonte="FCA_2025_2026_COTAHIST",
                prioridade=90,
            )
        elif status == "FORA_UNIVERSO_SISTEMA":
            _adicionar(
                evidencias,
                ticker=ticker,
                cd_cvm=linha["CD_CVM"],
                status="FORA_UNIVERSO_SISTEMA",
                fonte="FCA_2025_2026_COTAHIST",
                prioridade=90,
            )

    # 2. GetInitialCompanies + GetDetail da B3.
    for linha in b3:
        if linha["STATUS"] == "RESOLVIDO_B3_EXATO":
            _adicionar(
                evidencias,
                ticker=linha["TICKER"],
                cd_cvm=linha["CD_CVM"],
                status="RESOLVIDO_B3_EXATO",
                fonte="B3_GETDETAIL",
                prioridade=80,
            )
        elif linha["STATUS"] == "CD_CVM_B3_FORA_SISTEMA":
            _adicionar(
                evidencias,
                ticker=linha["TICKER"],
                cd_cvm=linha["CD_CVM"],
                status="FORA_UNIVERSO_SISTEMA",
                fonte="B3_LISTED_COMPANIES",
                prioridade=80,
            )

    # 3. FCA 2024.
    for linha in fca24:
        if linha["STATUS"] == "RESOLVIDO_FCA_2024":
            _adicionar(
                evidencias,
                ticker=linha["TICKER"],
                cd_cvm=linha["CD_CVM"],
                status="RESOLVIDO_FCA_2024",
                fonte="FCA_2024",
                prioridade=70,
            )
        elif linha["STATUS"] == "CD_CVM_FCA_2024_FORA_SISTEMA":
            _adicionar(
                evidencias,
                ticker=linha["TICKER"],
                cd_cvm=linha["CD_CVM"],
                status="FORA_UNIVERSO_SISTEMA",
                fonte="FCA_2024",
                prioridade=70,
            )

    # 4. FCA histórico 2010–2023.
    for linha in fcahist:
        if linha["STATUS"] == "RESOLVIDO_FCA_HISTORICO":
            _adicionar(
                evidencias,
                ticker=linha["TICKER"],
                cd_cvm=linha["CD_CVM"],
                status="RESOLVIDO_FCA_HISTORICO",
                fonte="FCA_2010_2023",
                prioridade=60,
            )
        elif linha["STATUS"] == "CD_CVM_FCA_HISTORICO_FORA_SISTEMA":
            _adicionar(
                evidencias,
                ticker=linha["TICKER"],
                cd_cvm=linha["CD_CVM"],
                status="FORA_UNIVERSO_SISTEMA",
                fonte="FCA_2010_2023",
                prioridade=60,
            )

    # 5. Exceções documentais auditadas individualmente.
    excecao_por_ticker = {}
    for linha in excecoes:
        ticker = linha["TICKER"].strip().upper()
        excecao_por_ticker[ticker] = linha
        _adicionar(
            evidencias,
            ticker=ticker,
            cd_cvm=linha["CD_CVM"],
            status=linha["STATUS"],
            fonte=linha["FONTE"],
            prioridade=100,
        )

    reconciliados = []
    revisao = []

    for linha in sorted(universo, key=lambda x: x["TICKER"]):
        ticker = linha["TICKER"].strip().upper()
        resultado = resolver_evidencias(
            ticker,
            evidencias.get(ticker, []),
        )

        cd_cvm = resultado.cd_cvm or ""
        dentro = resultado.status not in {
            "FORA_UNIVERSO_SISTEMA",
            "NAO_RESOLVIDO",
            "CONFLITO",
        }

        problemas = []

        if resultado.status in {"NAO_RESOLVIDO", "CONFLITO"}:
            problemas.append(resultado.conflito or resultado.status)

        if dentro:
            if not cd_cvm:
                problemas.append("RESOLVIDO_SEM_CD_CVM")
            elif cd_cvm not in sistema:
                problemas.append("CD_CVM_RESOLVIDO_FORA_DAS_499")
        elif resultado.status == "FORA_UNIVERSO_SISTEMA":
            if cd_cvm and cd_cvm in sistema:
                problemas.append("FORA_UNIVERSO_MAS_CD_CVM_ESTA_NAS_499")

        exc = excecao_por_ticker.get(ticker, {})

        item = {
            "TICKER": ticker,
            "CD_CVM": cd_cvm,
            "DENOM_CIA": (
                sistema[cd_cvm]["nome"]
                if cd_cvm in sistema
                else ""
            ),
            "TIPO_ATIVO": linha["TIPO_ATIVO"],
            "CLASSE": linha["CLASSE"],
            "PRIMEIRA_DATA_2025": linha["PRIMEIRA_DATA_2025"],
            "ULTIMA_DATA_2025": linha["ULTIMA_DATA_2025"],
            "PREGOES_2025": linha["PREGOES_2025"],
            "ISINS_2025": linha["ISINS_2025"],
            "STATUS_FINAL": resultado.status,
            "FONTES": "|".join(resultado.fontes),
            "VINCULO_EXCEPCIONAL": exc.get("VINCULO", ""),
            "DT_INICIO_VALIDADA": exc.get("DT_INICIO", ""),
            "DT_FIM_VALIDADA": exc.get("DT_FIM", ""),
            "PROBLEMAS": "|".join(problemas),
        }
        reconciliados.append(item)

        if problemas:
            revisao.append(
                {
                    "NIVEL": "TICKER",
                    "CHAVE": ticker,
                    "DETALHE": "|".join(problemas),
                }
            )

    # Forma grupos econômicos apenas com tickers ligados às 499 empresas.
    por_grupo: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for item in reconciliados:
        if item["PROBLEMAS"]:
            continue
        if item["STATUS_FINAL"] == "FORA_UNIVERSO_SISTEMA":
            continue
        por_grupo[
            (
                item["CD_CVM"],
                item["TIPO_ATIVO"],
                item["CLASSE"],
            )
        ].append(item)

    grupos = []
    for (cd_cvm, tipo, classe), itens in sorted(por_grupo.items()):
        itens = sorted(
            itens,
            key=lambda x: (
                x["PRIMEIRA_DATA_2025"],
                x["TICKER"],
            ),
        )

        sobreposicoes = []
        for i, atual in enumerate(itens):
            ini_a = _data(atual["PRIMEIRA_DATA_2025"])
            fim_a = _data(atual["ULTIMA_DATA_2025"])

            for proximo in itens[i + 1:]:
                ini_b = _data(proximo["PRIMEIRA_DATA_2025"])
                fim_b = _data(proximo["ULTIMA_DATA_2025"])

                if ini_b > fim_a:
                    break

                if ini_a <= fim_b and ini_b <= fim_a:
                    # O mesmo instrumento/classificação com dois tickers
                    # negociando na mesma data precisa de revisão.
                    sobreposicoes.append(
                        f"{atual['TICKER']}~{proximo['TICKER']}"
                    )

        problemas = ""
        if sobreposicoes:
            problemas = (
                "SOBREPOSICAO_TICKERS_MESMA_COMPANHIA_CLASSE:"
                + ",".join(sobreposicoes)
            )
            revisao.append(
                {
                    "NIVEL": "GRUPO",
                    "CHAVE": f"{cd_cvm}|{tipo}|{classe}",
                    "DETALHE": problemas,
                }
            )

        grupos.append(
            {
                "CHAVE_CANDIDATO": f"{cd_cvm}|{tipo}|{classe}",
                "CD_CVM": cd_cvm,
                "DENOM_CIA": sistema[cd_cvm]["nome"],
                "TIPO_ATIVO": tipo,
                "CLASSE": classe,
                "TICKERS_2025": "|".join(
                    item["TICKER"] for item in itens
                ),
                "QTD_TICKERS_2025": len(itens),
                "ISINS_2025": "|".join(sorted({
                    isin
                    for item in itens
                    for isin in item["ISINS_2025"].split("|")
                    if isin
                })),
                "PRIMEIRA_DATA_2025": min(
                    item["PRIMEIRA_DATA_2025"] for item in itens
                ),
                "ULTIMA_DATA_2025": max(
                    item["ULTIMA_DATA_2025"] for item in itens
                ),
                "STATUS": (
                    "REVISAO" if problemas
                    else "CANDIDATO_APROVADO"
                ),
                "PROBLEMAS": problemas,
            }
        )

    _escrever(
        SAIDA_TICKERS,
        reconciliados,
        [
            "TICKER",
            "CD_CVM",
            "DENOM_CIA",
            "TIPO_ATIVO",
            "CLASSE",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
            "PREGOES_2025",
            "ISINS_2025",
            "STATUS_FINAL",
            "FONTES",
            "VINCULO_EXCEPCIONAL",
            "DT_INICIO_VALIDADA",
            "DT_FIM_VALIDADA",
            "PROBLEMAS",
        ],
    )
    _escrever(
        SAIDA_GRUPOS,
        grupos,
        [
            "CHAVE_CANDIDATO",
            "CD_CVM",
            "DENOM_CIA",
            "TIPO_ATIVO",
            "CLASSE",
            "TICKERS_2025",
            "QTD_TICKERS_2025",
            "ISINS_2025",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
            "STATUS",
            "PROBLEMAS",
        ],
    )
    _escrever(
        SAIDA_REVISAO,
        revisao,
        ["NIVEL", "CHAVE", "DETALHE"],
    )

    dentro = [
        item for item in reconciliados
        if not item["PROBLEMAS"]
        and item["STATUS_FINAL"] != "FORA_UNIVERSO_SISTEMA"
    ]
    fora = [
        item for item in reconciliados
        if not item["PROBLEMAS"]
        and item["STATUS_FINAL"] == "FORA_UNIVERSO_SISTEMA"
    ]
    multi = [
        item for item in grupos
        if int(item["QTD_TICKERS_2025"]) > 1
    ]

    gate = (
        len(reconciliados) == len(universo)
        and len(dentro) + len(fora) == len(universo)
        and len(revisao) == 0
    )

    print("=" * 96)
    print("SISTEMA CVM — D.4 — GATE FINAL DO UNIVERSO 2025")
    print("=" * 96)
    print(f"Tickers observados no COTAHIST 2025: {len(universo):,}")
    print(f"Tickers ligados às 499 empresas: {len(dentro):,}")
    print(f"Tickers fora do universo contábil: {len(fora):,}")
    print(f"Tickers não resolvidos/conflitantes: {len(revisao):,}")
    print(f"Grupos candidatos de instrumentos: {len(grupos):,}")
    print(
        "Grupos com múltiplos tickers em 2025: "
        f"{len(multi):,}"
    )
    print(f"GATE_APROVADO: {gate}")
    print()

    if multi:
        print("CONTINUIDADES / GRUPOS MULTITICKER")
        print("-" * 96)
        for item in multi:
            print(
                f"{item['CD_CVM']} | "
                f"{item['TIPO_ATIVO']}/{item['CLASSE']} | "
                f"{item['TICKERS_2025']} | {item['STATUS']}"
            )
        print()

    if revisao:
        print("REVISÃO")
        print("-" * 96)
        for item in revisao:
            print(
                f"{item['NIVEL']:6s} | "
                f"{item['CHAVE']:24s} | "
                f"{item['DETALHE']}"
            )
        print()

    print(f"Tickers: {SAIDA_TICKERS}")
    print(f"Grupos: {SAIDA_GRUPOS}")
    print(f"Revisão: {SAIDA_REVISAO}")
    print()

    if gate:
        print("RESULTADO: APROVADO")
        print(
            "O universo 2025 foi integralmente classificado sem conflito. "
            "Nenhum novo INSTRUMENTO_ID foi criado."
        )
    else:
        print("RESULTADO: REVISÃO NECESSÁRIA")
        print(
            "A promoção do catálogo permanece bloqueada até zerar "
            "as inconsistências."
        )


if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import duckdb


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.catalogo import carregar_catalogo_referencia  # noqa: E402
from src.mercado.identidade import resolver_instrumento  # noqa: E402
from src.mercado.promocao_catalogo import sha256_arquivo  # noqa: E402
from src.mercado.providers.b3_cotahist import iterar_cotacoes  # noqa: E402
from src.mercado.schema import criar_schema_identidade  # noqa: E402


REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
CANDIDATE_DIR = REPORTS_DIR / "catalogo_temporal_2025"
RECONCILIADOS = REPORTS_DIR / "universo_2025_reconciliado_tickers.csv"
ALOCACOES = REPORTS_DIR / "catalogo_ampliado_alocacoes_2025.csv"
PROMOCAO = REPORTS_DIR / "promocao_catalogo_temporal_2025.json"

ESPERADO = {
    "instrumentos": 380,
    "tickers": 391,
    "identificadores": 390,
}

ARQUIVOS = (
    "instrumentos.csv",
    "tickers_historico.csv",
    "identificadores.csv",
)


def _ler(caminho: Path, delimitador: str) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=delimitador))


def _falha(falhas: list[str], condicao: bool, mensagem: str) -> None:
    if not condicao:
        falhas.append(mensagem)


def _catalogo_cvm() -> set[str]:
    con = conectar_cvm(read_only=True)
    try:
        return {
            str(x[0]).strip().zfill(6)
            for x in con.execute("SELECT CD_CVM FROM empresas").fetchall()
        }
    finally:
        con.close()


def _resumir_cotahist(
    caminho: Path,
    *,
    ano: int,
    tickers_alvo: set[str],
) -> dict[str, tuple[object, object, int]]:
    resumo: dict[str, list] = {}
    for cotacao in iterar_cotacoes(caminho):
        if cotacao.data.year != ano:
            raise RuntimeError(
                f"{caminho.name}: registro {cotacao.data} fora de {ano}."
            )
        if cotacao.tipo_mercado != "010":
            continue
        if cotacao.ticker not in tickers_alvo:
            continue

        item = resumo.setdefault(
            cotacao.ticker,
            [cotacao.data, cotacao.data, 0],
        )
        item[0] = min(item[0], cotacao.data)
        item[1] = max(item[1], cotacao.data)
        item[2] += 1

    return {
        ticker: (item[0], item[1], item[2])
        for ticker, item in resumo.items()
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Uso: python tests/mercado/auditoria_catalogo_promovido_2025.py "
            "<COTAHIST_A2024.ZIP> <COTAHIST_A2025.ZIP>"
        )

    caminhos = {
        2024: Path(sys.argv[1]),
        2025: Path(sys.argv[2]),
    }
    falhas: list[str] = []

    print("=" * 104)
    print("SISTEMA CVM — D.4 — AUDITORIA ADVERSARIAL PÓS-PROMOÇÃO DO CATÁLOGO")
    print("=" * 104)

    for nome in ARQUIVOS:
        oficial = REFERENCE_DIR / nome
        candidato = CANDIDATE_DIR / nome
        _falha(
            falhas,
            oficial.is_file() and candidato.is_file(),
            f"{nome}: arquivo oficial/candidato ausente.",
        )
        if oficial.is_file() and candidato.is_file():
            _falha(
                falhas,
                sha256_arquivo(oficial) == sha256_arquivo(candidato),
                f"{nome}: oficial diverge byte a byte do candidato aprovado.",
            )

    con = duckdb.connect(":memory:")
    try:
        criar_schema_identidade(con)
        resumo = carregar_catalogo_referencia(con)
        _falha(
            falhas,
            resumo == ESPERADO,
            f"Contagens promovidas divergentes: {resumo} != {ESPERADO}",
        )

        # IDs novos devem ser exatamente 5004..5375; os oito IDs piloto
        # anteriores permanecem presentes e nunca são renumerados.
        ids = [
            int(x[0])
            for x in con.execute(
                "SELECT INSTRUMENTO_ID FROM instrumentos ORDER BY INSTRUMENTO_ID"
            ).fetchall()
        ]
        novos = [x for x in ids if x > 5003]
        _falha(
            falhas,
            novos == list(range(5004, 5376)),
            "Faixa de novos INSTRUMENTO_ID não é exatamente 5004..5375.",
        )

        # Fixtures históricas que não podem mudar.
        fixtures = [
            ("PETR3", "2025-01-02", 1001),
            ("PETR4", "2025-01-02", 1002),
            ("TAEE11", "2025-01-02", 2001),
            ("ELET3", "2025-11-07", 3001),
            ("AXIA3", "2025-11-10", 3001),
            ("MGLU3", "2024-05-27", 4001),
            ("NATU3", "2019-12-17", 5001),
            ("NTCO3", "2019-12-18", 5002),
            ("NTCO3", "2025-07-01", 5002),
            ("NATU3", "2025-07-02", 5003),
        ]
        for ticker, data_ref, esperado_id in fixtures:
            try:
                obtido = resolver_instrumento(
                    con,
                    bolsa="B3",
                    ticker=ticker,
                    data_referencia=data_ref,
                )
            except Exception as exc:
                falhas.append(
                    f"Fixture {ticker}|{data_ref}: {type(exc).__name__}: {exc}"
                )
                continue
            _falha(
                falhas,
                obtido == esperado_id,
                f"Fixture {ticker}|{data_ref}: {obtido} != {esperado_id}",
            )

        # Todo instrumento promovido precisa de ao menos uma vigência de ticker.
        sem_ticker = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM instrumentos i
                LEFT JOIN tickers_historico t
                  ON t.INSTRUMENTO_ID = i.INSTRUMENTO_ID
                WHERE t.INSTRUMENTO_ID IS NULL
                """
            ).fetchone()[0]
        )
        _falha(
            falhas,
            sem_ticker == 0,
            f"Instrumentos sem ticker: {sem_ticker}",
        )

        # Vigência de ticker e ISIN não pode escapar da vida do instrumento.
        ticker_fora = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM tickers_historico t
                JOIN instrumentos i USING (INSTRUMENTO_ID)
                WHERE t.DT_INICIO < i.DT_INICIO
                   OR (
                        i.DT_FIM IS NOT NULL
                        AND (
                            t.DT_FIM IS NULL
                            OR t.DT_FIM > i.DT_FIM
                        )
                   )
                """
            ).fetchone()[0]
        )
        _falha(
            falhas,
            ticker_fora == 0,
            f"Vigências de ticker fora do instrumento: {ticker_fora}",
        )

        isin_fora = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM instrumentos_identificadores x
                JOIN instrumentos i USING (INSTRUMENTO_ID)
                WHERE x.DT_INICIO < i.DT_INICIO
                   OR (
                        i.DT_FIM IS NOT NULL
                        AND (
                            x.DT_FIM IS NULL
                            OR x.DT_FIM > i.DT_FIM
                        )
                   )
                """
            ).fetchone()[0]
        )
        _falha(
            falhas,
            isin_fora == 0,
            f"Vigências de ISIN fora do instrumento: {isin_fora}",
        )

        # ISINs distintos simultâneos no mesmo instrumento são bloqueantes.
        isin_sobreposto = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM instrumentos_identificadores a
                JOIN instrumentos_identificadores b
                  ON a.INSTRUMENTO_ID = b.INSTRUMENTO_ID
                 AND a.TIPO_IDENTIFICADOR = 'ISIN'
                 AND b.TIPO_IDENTIFICADOR = 'ISIN'
                 AND a.VALOR < b.VALOR
                 AND a.DT_INICIO < COALESCE(b.DT_FIM, DATE '9999-12-31')
                 AND b.DT_INICIO < COALESCE(a.DT_FIM, DATE '9999-12-31')
                """
            ).fetchone()[0]
        )
        _falha(
            falhas,
            isin_sobreposto == 0,
            f"ISINs distintos sobrepostos: {isin_sobreposto}",
        )

        reconciliados = _ler(RECONCILIADOS, ";")
        alocacoes = _ler(ALOCACOES, ";")
        por_chave = {
            x["CHAVE_CANDIDATO"].strip(): int(x["INSTRUMENTO_ID"])
            for x in alocacoes
        }

        alvo_2025 = {}
        for linha in reconciliados:
            if linha["PROBLEMAS"].strip():
                continue
            if linha["STATUS_FINAL"].strip().upper() == "FORA_UNIVERSO_SISTEMA":
                continue

            ticker = linha["TICKER"].strip().upper()
            chave = (
                f"{linha['CD_CVM'].strip().zfill(6)}|"
                f"{linha['TIPO_ATIVO'].strip().upper()}|"
                f"{linha['CLASSE'].strip().upper()}"
            )
            esperado_id = por_chave[chave]
            alvo_2025[ticker] = esperado_id

            for campo in ("PRIMEIRA_DATA_2025", "ULTIMA_DATA_2025"):
                try:
                    obtido = resolver_instrumento(
                        con,
                        bolsa="B3",
                        ticker=ticker,
                        data_referencia=linha[campo],
                    )
                except Exception as exc:
                    falhas.append(
                        f"{ticker}|{linha[campo]}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue
                _falha(
                    falhas,
                    obtido == esperado_id,
                    f"{ticker}|{linha[campo]}: {obtido} != {esperado_id}",
                )

        _falha(
            falhas,
            len(alvo_2025) == 389,
            f"Tickers reconciliados dentro do sistema: {len(alvo_2025)} != 389",
        )

        # COTAHIST 2024/2025: todo ticker-alvo observado deve resolver nas
        # extremidades da janela observada. Em 2025 também precisa resolver
        # para o ID aprovado no gate.
        for ano, caminho in caminhos.items():
            if not caminho.is_file():
                raise FileNotFoundError(caminho)
            observado = _resumir_cotahist(
                caminho,
                ano=ano,
                tickers_alvo=set(alvo_2025),
            )
            for ticker, (primeira, ultima, _) in observado.items():
                for data_ref in (primeira, ultima):
                    try:
                        obtido = resolver_instrumento(
                            con,
                            bolsa="B3",
                            ticker=ticker,
                            data_referencia=data_ref,
                        )
                    except Exception as exc:
                        falhas.append(
                            f"COTAHIST {ano} {ticker}|{data_ref}: "
                            f"{type(exc).__name__}: {exc}"
                        )
                        continue
                    if ano == 2025:
                        _falha(
                            falhas,
                            obtido == alvo_2025[ticker],
                            f"COTAHIST 2025 {ticker}|{data_ref}: "
                            f"{obtido} != {alvo_2025[ticker]}",
                        )

    finally:
        con.close()

    catalogo_cvm = _catalogo_cvm()
    instrumentos = _ler(REFERENCE_DIR / "instrumentos.csv", ",")
    ausentes = sorted({
        x["CD_CVM"].strip().zfill(6)
        for x in instrumentos
        if x["CD_CVM"].strip().zfill(6) not in catalogo_cvm
    })
    _falha(
        falhas,
        not ausentes,
        f"CD_CVM promovidos ausentes do catálogo CVM: {ausentes}",
    )

    if PROMOCAO.is_file():
        payload = json.loads(PROMOCAO.read_text(encoding="utf-8"))
        for caminho_str, hash_antes in payload.get(
            "hashes_protegidos", {}
        ).items():
            caminho = Path(caminho_str)
            _falha(
                falhas,
                caminho.is_file(),
                f"Arquivo protegido desapareceu: {caminho}",
            )
            if caminho.is_file():
                _falha(
                    falhas,
                    sha256_arquivo(caminho) == hash_antes,
                    f"Arquivo protegido mudou após promoção: {caminho}",
                )
    else:
        falhas.append("Relatório local da promoção não encontrado.")

    print("RESUMO")
    print("-" * 104)
    print(f"Instrumentos: {ESPERADO['instrumentos']}")
    print(f"Vigências de ticker: {ESPERADO['tickers']}")
    print(f"ISIN/identificadores: {ESPERADO['identificadores']}")
    print("Novos IDs esperados: 5004–5375 (372)")
    print(f"Tickers 2025 auditados: 389")
    print(f"Falhas: {len(falhas)}")
    print()

    if falhas:
        print("FALHAS — BLOQUEANTES")
        print("-" * 104)
        for item in falhas[:100]:
            print(f"- {item}")
        if len(falhas) > 100:
            print(f"... e mais {len(falhas) - 100} falha(s).")
        print()
        print("RESULTADO: BLOQUEADO")
        raise RuntimeError(
            "Auditoria pós-promoção falhou; não liberar 2010–2023."
        )

    print("GATE_APROVADO: True")
    print("RESULTADO: AUDITORIA PÓS-PROMOÇÃO APROVADA")
    print(
        "Catálogo oficial promovido e íntegro. A decisão de liberar a carga "
        "2010–2023 deve ocorrer somente após versionar este estado."
    )


if __name__ == "__main__":
    main()

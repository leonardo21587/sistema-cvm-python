from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.arquivos import preservar_arquivo_raw  # noqa: E402
from src.mercado.catalogo import tickers_catalogados  # noqa: E402
from src.mercado.identidade import InstrumentoNaoEncontrado  # noqa: E402
from src.mercado.ingestao import cotacao_para_preco, persistir_preco  # noqa: E402
from src.mercado.providers.b3_cotahist import iterar_cotacoes  # noqa: E402
from src.mercado.schema import conectar_mercado  # noqa: E402
from src.mercado.validacao import validar_gate_piloto  # noqa: E402


STAGING_DB = (
    ROOT_DIR
    / "data"
    / "market"
    / "staging"
    / "mercado_piloto_2025.duckdb"
)
BANCO_CVM = ROOT_DIR / "data" / "processed" / "sistema_cvm.duckdb"

ANO = 2025
FONTE = "B3_COTAHIST"
BOLSA = "B3"
TIPO_MERCADO_VISTA = "010"
REGISTROS_ESPERADOS = 1500


def executar(caminho_cotahist: Path) -> None:
    if not caminho_cotahist.is_file():
        raise FileNotFoundError(caminho_cotahist)

    if not STAGING_DB.is_file():
        raise FileNotFoundError(
            "Staging do piloto 2025 não existe. "
            "Execute primeiro piloto_ingestao_2025.py."
        )

    raw = preservar_arquivo_raw(
        caminho_cotahist,
        fonte="b3",
        ano=ANO,
    )

    con = conectar_mercado(STAGING_DB, read_only=False)

    try:
        tickers = tickers_catalogados()

        inseridos = 0
        iguais = 0
        atualizados = 0
        sem_instrumento = 0
        elegiveis = 0

        for cotacao in iterar_cotacoes(caminho_cotahist):
            if (
                cotacao.tipo_mercado != TIPO_MERCADO_VISTA
                or cotacao.ticker not in tickers
            ):
                continue

            elegiveis += 1

            try:
                preco = cotacao_para_preco(
                    con,
                    cotacao,
                    bolsa=BOLSA,
                    fonte=FONTE,
                    arquivo_fonte=caminho_cotahist.name,
                )
            except InstrumentoNaoEncontrado:
                sem_instrumento += 1
                continue

            resultado = persistir_preco(con, preco)

            if resultado == "INSERIDO":
                inseridos += 1
            elif resultado == "IGUAL":
                iguais += 1
            elif resultado == "ATUALIZADO":
                atualizados += 1
            else:
                raise RuntimeError(
                    f"Resultado de persistência inesperado: {resultado}"
                )

        total_precos = int(
            con.execute(
                "SELECT COUNT(*) FROM precos_diarios"
            ).fetchone()[0]
        )
        total_substituicoes = int(
            con.execute(
                "SELECT COUNT(*) FROM precos_substituicoes"
            ).fetchone()[0]
        )

        gate = validar_gate_piloto(
            con,
            caminho_cvm=BANCO_CVM,
        )

        print("=" * 78)
        print("SISTEMA CVM — D.3 — REPLAY REAL COTAHIST 2025")
        print("=" * 78)
        print(f"Arquivo: {caminho_cotahist}")
        print(f"SHA-256: {raw.sha256}")
        print(f"Elegíveis: {elegiveis:,}")
        print(f"Inseridos: {inseridos:,}")
        print(f"Iguais: {iguais:,}")
        print(f"Atualizados: {atualizados:,}")
        print(f"Sem instrumento: {sem_instrumento:,}")
        print(f"Total em precos_diarios: {total_precos:,}")
        print(f"Total em precos_substituicoes: {total_substituicoes:,}")
        print(f"Gate aprovado: {gate['aprovado']}")
        print()

        falhas = []

        if elegiveis != REGISTROS_ESPERADOS:
            falhas.append(
                f"Elegíveis {elegiveis} != {REGISTROS_ESPERADOS}."
            )
        if inseridos != 0:
            falhas.append(
                f"Replay inseriu {inseridos} linha(s); esperado 0."
            )
        if iguais != REGISTROS_ESPERADOS:
            falhas.append(
                f"Iguais {iguais} != {REGISTROS_ESPERADOS}."
            )
        if atualizados != 0:
            falhas.append(
                f"Replay atualizou {atualizados} linha(s); esperado 0."
            )
        if sem_instrumento != 0:
            falhas.append(
                f"{sem_instrumento} linha(s) sem instrumento."
            )
        if total_precos != REGISTROS_ESPERADOS:
            falhas.append(
                f"Banco tem {total_precos} preços; "
                f"esperado {REGISTROS_ESPERADOS}."
            )
        if total_substituicoes != 0:
            falhas.append(
                f"Log contém {total_substituicoes} substituição(ões); "
                "esperado 0 no replay idêntico."
            )
        if not gate["aprovado"]:
            falhas.append("Gate de integridade deixou de estar verde.")

        if falhas:
            print("RESULTADO: BLOQUEADO")
            for falha in falhas:
                print(f"- {falha}")
            raise RuntimeError(
                "Replay real de 2025 não foi idempotente."
            )

        print("RESULTADO: APROVADO")
        print("Replay real idempotente: 1.500/1.500 linhas IGUAIS.")
        print("Nenhuma inserção, atualização ou substituição indevida.")

    finally:
        con.close()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python tests/mercado/replay_ingestao_2025.py "
            "<caminho_para_COTAHIST_A2025.ZIP>"
        )

    executar(Path(sys.argv[1]))


if __name__ == "__main__":
    main()

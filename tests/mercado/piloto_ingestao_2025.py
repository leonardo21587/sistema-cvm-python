from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.arquivos import preservar_arquivo_raw  # noqa: E402
from src.mercado.catalogo import (  # noqa: E402
    carregar_catalogo_referencia,
    tickers_catalogados,
)
from src.mercado.identidade import InstrumentoNaoEncontrado  # noqa: E402
from src.mercado.ingestao import (  # noqa: E402
    cotacao_para_preco,
    persistir_preco,
)
from src.mercado.providers.b3_cotahist import iterar_cotacoes  # noqa: E402
from src.mercado.relatorio_ingestao import (  # noqa: E402
    novo_relatorio_ingestao,
    salvar_relatorio_ingestao,
)
from src.mercado.schema import (  # noqa: E402
    conectar_mercado,
    criar_schema_mercado,
)
from src.mercado.validacao import (  # noqa: E402
    detectar_descontinuidades,
    validar_gate_piloto,
)


STAGING_DIR = ROOT_DIR / "data" / "market" / "staging"
REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
BANCO_CVM = ROOT_DIR / "data" / "processed" / "sistema_cvm.duckdb"
STAGING_DB = STAGING_DIR / "mercado_piloto_2025.duckdb"

ANO = 2025
FONTE = "B3_COTAHIST"
BOLSA = "B3"
TIPO_MERCADO_VISTA = "010"
REGISTROS_ESPERADOS_PILOTO = 1500


def executar(caminho_cotahist: Path) -> None:
    if not caminho_cotahist.is_file():
        raise FileNotFoundError(caminho_cotahist)

    if not BANCO_CVM.is_file():
        raise FileNotFoundError(
            f"Banco CVM necessário ao gate não existe: {BANCO_CVM}"
        )

    raw = preservar_arquivo_raw(
        caminho_cotahist,
        fonte="b3",
        ano=ANO,
    )

    relatorio = novo_relatorio_ingestao(
        fonte=FONTE,
        ano=ANO,
        arquivo_fonte=caminho_cotahist.name,
        sha256_raw=raw.sha256,
    )

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if STAGING_DB.exists():
        STAGING_DB.unlink()

    con = conectar_mercado(STAGING_DB, read_only=False)

    try:
        criar_schema_mercado(con)
        resumo_catalogo = carregar_catalogo_referencia(con)
        tickers = tickers_catalogados()

        print("=" * 78)
        print("SISTEMA CVM — D.3 — INGESTÃO CONTROLADA COTAHIST 2025")
        print("=" * 78)
        print(f"Arquivo: {caminho_cotahist}")
        print(f"SHA-256: {raw.sha256}")
        print(f"Staging: {STAGING_DB}")
        print(
            "Catálogo piloto: "
            f"{resumo_catalogo['instrumentos']} instrumentos | "
            f"{resumo_catalogo['tickers']} vigências de ticker"
        )
        print()

        por_ticker: dict[str, int] = {ticker: 0 for ticker in tickers}

        for cotacao in iterar_cotacoes(caminho_cotahist):
            relatorio.linhas_cotacao += 1

            if (
                cotacao.tipo_mercado != TIPO_MERCADO_VISTA
                or cotacao.ticker not in tickers
            ):
                relatorio.linhas_fora_escopo += 1
                continue

            relatorio.linhas_elegiveis += 1

            try:
                preco = cotacao_para_preco(
                    con,
                    cotacao,
                    bolsa=BOLSA,
                    fonte=FONTE,
                    arquivo_fonte=caminho_cotahist.name,
                )
            except InstrumentoNaoEncontrado:
                relatorio.linhas_sem_instrumento += 1
                continue

            relatorio.linhas_mapeadas += 1
            por_ticker[cotacao.ticker] += 1

            resultado = persistir_preco(con, preco)
            relatorio.registrar_persistencia(resultado)

        # Header + trailer existem no arquivo anual oficial.
        relatorio.linhas_brutas = relatorio.linhas_cotacao + 2

        descontinuidades = detectar_descontinuidades(
            con,
            limiar_abs_log=0.35,
        )
        relatorio.descontinuidades_sinalizadas = len(descontinuidades)

        gate = validar_gate_piloto(
            con,
            caminho_cvm=BANCO_CVM,
        )

        falhas = []

        if relatorio.linhas_mapeadas != REGISTROS_ESPERADOS_PILOTO:
            falhas.append(
                "Quantidade mapeada diferente da reconciliação prévia: "
                f"{relatorio.linhas_mapeadas} != "
                f"{REGISTROS_ESPERADOS_PILOTO}."
            )

        if relatorio.linhas_sem_instrumento != 0:
            falhas.append(
                f"{relatorio.linhas_sem_instrumento} linhas elegíveis "
                "sem instrumento resolvido."
            )

        if not gate["aprovado"]:
            falhas.append(
                "Gate de integridade bloqueado: "
                f"identidade={len(gate['falhas_identidade'])}; "
                f"preços_fora_vigencia={gate['precos_fora_vigencia']}; "
                f"cd_cvm_ausentes={gate['cd_cvm_ausentes']}."
            )

        total_banco = int(
            con.execute("SELECT COUNT(*) FROM precos_diarios").fetchone()[0]
        )

        if total_banco != REGISTROS_ESPERADOS_PILOTO:
            falhas.append(
                f"precos_diarios contém {total_banco} linhas; "
                f"esperado {REGISTROS_ESPERADOS_PILOTO}."
            )

        relatorio.falhas_invariantes = (
            len(gate["falhas_identidade"])
            + int(gate["precos_fora_vigencia"])
            + len(gate["cd_cvm_ausentes"])
        )

        status = "BLOQUEADO" if falhas else "APROVADO"
        relatorio.finalizar(
            status=status,
            observacoes=" | ".join(falhas),
        )

        json_path, csv_path = salvar_relatorio_ingestao(
            relatorio,
            diretorio=REPORTS_DIR,
        )

        print("RESUMO")
        print("-" * 78)
        print(f"Registros 01 lidos: {relatorio.linhas_cotacao:,}")
        print(f"Fora do escopo do piloto: {relatorio.linhas_fora_escopo:,}")
        print(f"Elegíveis no catálogo piloto: {relatorio.linhas_elegiveis:,}")
        print(f"Mapeados: {relatorio.linhas_mapeadas:,}")
        print(f"Sem instrumento: {relatorio.linhas_sem_instrumento:,}")
        print(f"Inseridos: {relatorio.inseridos:,}")
        print(f"Iguais: {relatorio.iguais:,}")
        print(f"Atualizados: {relatorio.atualizados:,}")
        print(f"Descontinuidades sinalizadas: {len(descontinuidades):,}")
        print()

        print("COBERTURA POR TICKER")
        print("-" * 78)
        for ticker in sorted(por_ticker):
            print(f"{ticker:8s} | {por_ticker[ticker]:4d} registros")

        print()
        print("GATE")
        print("-" * 78)
        print(
            "Falhas de identidade: "
            f"{len(gate['falhas_identidade'])}"
        )
        print(
            "Preços fora da vigência: "
            f"{gate['precos_fora_vigencia']}"
        )
        print(
            "CD_CVM ausentes no catálogo CVM: "
            f"{gate['cd_cvm_ausentes']}"
        )
        print(f"Relatório JSON: {json_path}")
        print(f"Resumo CSV: {csv_path}")
        print()

        if descontinuidades:
            print("ALERTAS DE DESCONTINUIDADE — NÃO BLOQUEANTES")
            print("-" * 78)
            for item in descontinuidades[:20]:
                print(
                    f"ID {item.instrumento_id} | "
                    f"{item.data_anterior} -> {item.data_atual} | "
                    f"{item.fechamento_anterior:.4f} -> "
                    f"{item.fechamento_atual:.4f} | "
                    f"log={item.retorno_log:+.4f}"
                )
            if len(descontinuidades) > 20:
                print(
                    f"... e mais {len(descontinuidades) - 20} alerta(s)."
                )
            print()

        if falhas:
            print("RESULTADO: BLOQUEADO")
            for falha in falhas:
                print(f"- {falha}")
            raise RuntimeError(
                "Piloto 2025 não pode ser promovido."
            )

        print("RESULTADO: APROVADO")
        print(
            "Staging 2025 validado; nenhum dado foi promovido "
            "para data/processed/mercado.duckdb."
        )

    finally:
        con.close()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python tests/mercado/piloto_ingestao_2025.py "
            "<caminho_para_COTAHIST_A2025.ZIP>"
        )

    executar(Path(sys.argv[1]))


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.arquivos import preservar_arquivo_raw  # noqa: E402
from src.mercado.catalogo import carregar_catalogo_referencia  # noqa: E402
from src.mercado.carga_historica import carregar_cotahist_catalogado  # noqa: E402
from src.mercado.relatorio_ingestao import (  # noqa: E402
    novo_relatorio_ingestao,
    salvar_relatorio_ingestao,
)
from src.mercado.schema import conectar_mercado, criar_schema_mercado  # noqa: E402
from src.mercado.validacao import (  # noqa: E402
    detectar_descontinuidades,
    validar_gate_piloto,
)


STAGING_DIR = ROOT_DIR / "data" / "market" / "staging"
REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
BANCO_CVM = ROOT_DIR / "data" / "processed" / "sistema_cvm.duckdb"
STAGING_DB = STAGING_DIR / "mercado_curto_2024_2025.duckdb"

ANOS = (2024, 2025)
TICKERS_ESPERADOS_2024 = {"PETR3", "PETR4", "TAEE11", "ELET3", "MGLU3", "NTCO3"}
TICKERS_PROIBIDOS_2024 = {"AXIA3", "NATU3"}
TICKERS_ESPERADOS_2025 = {
    "PETR3", "PETR4", "TAEE11", "ELET3", "AXIA3", "MGLU3", "NTCO3", "NATU3"
}


def _salvar_relatorio_ano(resultado, raw, caminho):
    relatorio = novo_relatorio_ingestao(
        fonte="B3_COTAHIST",
        ano=resultado.ano,
        arquivo_fonte=caminho.name,
        sha256_raw=raw.sha256,
    )
    relatorio.linhas_cotacao = resultado.linhas_cotacao
    relatorio.linhas_brutas = resultado.linhas_cotacao + 2
    relatorio.linhas_fora_escopo = resultado.linhas_fora_escopo
    relatorio.linhas_elegiveis = resultado.linhas_elegiveis
    relatorio.linhas_mapeadas = resultado.linhas_mapeadas
    relatorio.linhas_sem_instrumento = resultado.linhas_sem_instrumento
    relatorio.inseridos = resultado.inseridos
    relatorio.iguais = resultado.iguais
    relatorio.atualizados = resultado.atualizados
    relatorio.substituicoes = resultado.atualizados
    relatorio.finalizar(status="APROVADO")
    return salvar_relatorio_ingestao(
        relatorio,
        diretorio=REPORTS_DIR,
    )


def executar(caminho_2024: Path, caminho_2025: Path) -> None:
    caminhos = {2024: caminho_2024, 2025: caminho_2025}

    for ano, caminho in caminhos.items():
        if not caminho.is_file():
            raise FileNotFoundError(f"COTAHIST {ano} não encontrado: {caminho}")

    if not BANCO_CVM.is_file():
        raise FileNotFoundError(f"Banco CVM não encontrado: {BANCO_CVM}")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if STAGING_DB.exists():
        STAGING_DB.unlink()

    con = conectar_mercado(STAGING_DB, read_only=False)

    try:
        criar_schema_mercado(con)
        resumo_catalogo = carregar_catalogo_referencia(con)

        print("=" * 78)
        print("SISTEMA CVM — D.4 — CARGA CURTA REAL 2024–2025")
        print("=" * 78)
        print(f"Staging: {STAGING_DB}")
        print(
            f"Catálogo: {resumo_catalogo['instrumentos']} instrumentos | "
            f"{resumo_catalogo['tickers']} vigências de ticker"
        )
        print()

        resultados = {}
        total_mapeado = 0
        falhas = []

        for ano in ANOS:
            caminho = caminhos[ano]
            raw = preservar_arquivo_raw(
                caminho,
                fonte="b3",
                ano=ano,
            )

            resultado = carregar_cotahist_catalogado(
                con,
                caminho,
                ano=ano,
            )
            resultados[ano] = resultado
            total_mapeado += resultado.linhas_mapeadas

            _salvar_relatorio_ano(resultado, raw, caminho)

            print(f"ANO {ano}")
            print("-" * 78)
            print(f"Arquivo: {caminho.name}")
            print(f"SHA-256: {raw.sha256}")
            print(f"Registros 01: {resultado.linhas_cotacao:,}")
            print(f"Elegíveis: {resultado.linhas_elegiveis:,}")
            print(f"Mapeados: {resultado.linhas_mapeadas:,}")
            print(f"Sem instrumento: {resultado.linhas_sem_instrumento:,}")
            print(f"Inseridos: {resultado.inseridos:,}")
            print(f"Iguais: {resultado.iguais:,}")
            print(f"Atualizados: {resultado.atualizados:,}")

            presentes = {
                ticker
                for ticker, qtd in resultado.por_ticker.items()
                if qtd > 0
            }

            for ticker in sorted(presentes):
                print(
                    f"  {ticker:8s} | "
                    f"{resultado.por_ticker[ticker]:4d} registros"
                )

            if resultado.linhas_sem_instrumento != 0:
                falhas.append(
                    f"{ano}: {resultado.linhas_sem_instrumento} linha(s) "
                    "sem instrumento."
                )

            if resultado.linhas_elegiveis != resultado.linhas_mapeadas:
                falhas.append(
                    f"{ano}: elegíveis != mapeados "
                    f"({resultado.linhas_elegiveis} != "
                    f"{resultado.linhas_mapeadas})."
                )

            if resultado.atualizados != 0 or resultado.iguais != 0:
                falhas.append(
                    f"{ano}: staging novo deveria conter apenas inserções."
                )

            if ano == 2024:
                faltantes = TICKERS_ESPERADOS_2024 - presentes
                proibidos = TICKERS_PROIBIDOS_2024 & presentes
                if faltantes:
                    falhas.append(
                        f"2024: tickers esperados ausentes: {sorted(faltantes)}."
                    )
                if proibidos:
                    falhas.append(
                        f"2024: tickers temporalmente indevidos: {sorted(proibidos)}."
                    )

            if ano == 2025:
                faltantes = TICKERS_ESPERADOS_2025 - presentes
                if faltantes:
                    falhas.append(
                        f"2025: tickers esperados ausentes: {sorted(faltantes)}."
                    )

            print()

        total_banco = int(
            con.execute("SELECT COUNT(*) FROM precos_diarios").fetchone()[0]
        )
        total_substituicoes = int(
            con.execute("SELECT COUNT(*) FROM precos_substituicoes").fetchone()[0]
        )

        gate = validar_gate_piloto(
            con,
            caminho_cvm=BANCO_CVM,
        )
        descontinuidades = detectar_descontinuidades(
            con,
            limiar_abs_log=0.35,
        )

        if total_banco != total_mapeado:
            falhas.append(
                f"Banco contém {total_banco} linhas, mas cargas mapearam "
                f"{total_mapeado}."
            )

        if total_substituicoes != 0:
            falhas.append(
                f"Staging novo registrou {total_substituicoes} substituição(ões)."
            )

        if not gate["aprovado"]:
            falhas.append(
                "Gate final bloqueado: "
                f"identidade={len(gate['falhas_identidade'])}; "
                f"preços_fora_vigencia={gate['precos_fora_vigencia']}; "
                f"cd_cvm_ausentes={gate['cd_cvm_ausentes']}."
            )

        print("CONSOLIDADO 2024–2025")
        print("-" * 78)
        print(f"Total mapeado: {total_mapeado:,}")
        print(f"Total em precos_diarios: {total_banco:,}")
        print(f"Substituições: {total_substituicoes:,}")
        print(f"Descontinuidades não bloqueantes: {len(descontinuidades):,}")
        print(f"Gate aprovado: {gate['aprovado']}")
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
                print(f"... e mais {len(descontinuidades) - 20} alerta(s).")
            print()

        if falhas:
            print("RESULTADO: BLOQUEADO")
            for falha in falhas:
                print(f"- {falha}")
            raise RuntimeError(
                "Carga curta 2024–2025 não pode avançar."
            )

        print("RESULTADO: APROVADO")
        print(
            "Carga curta 2024–2025 validada em staging; "
            "mercado.duckdb oficial permanece intocado."
        )

    finally:
        con.close()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Uso: python tests/mercado/carga_curta_2024_2025.py "
            "<COTAHIST_A2024.ZIP> <COTAHIST_A2025.ZIP>"
        )

    executar(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()

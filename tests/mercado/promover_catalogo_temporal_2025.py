from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.promocao_catalogo import promover_catalogo  # noqa: E402


REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"
CANDIDATE_DIR = REPORTS_DIR / "catalogo_temporal_2025"

REVISAO = CANDIDATE_DIR / "revisao.csv"
MAPA = CANDIDATE_DIR / "mapa_tickers_2025.csv"
RELATORIO = REPORTS_DIR / "promocao_catalogo_temporal_2025.json"

BANCO_CVM = ROOT_DIR / "data" / "processed" / "sistema_cvm.duckdb"
BANCO_MERCADO = ROOT_DIR / "data" / "processed" / "mercado.duckdb"

CONTAGENS = {
    "instrumentos": 380,
    "tickers": 391,
    "identificadores": 390,
}


def _ler_semicolon(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def main() -> None:
    revisoes = _ler_semicolon(REVISAO)
    mapa = _ler_semicolon(MAPA)

    if revisoes:
        raise RuntimeError(
            f"Promoção bloqueada: revisão.csv contém {len(revisoes)} linha(s)."
        )
    if len(mapa) != 389:
        raise RuntimeError(
            f"Promoção bloqueada: mapa_tickers_2025={len(mapa)}; esperado=389."
        )

    protegidos = tuple(
        caminho
        for caminho in (BANCO_CVM, BANCO_MERCADO)
        if caminho.is_file()
    )

    print("=" * 100)
    print("SISTEMA CVM — D.4 — PROMOÇÃO CONTROLADA DO CATÁLOGO TEMPORAL")
    print("=" * 100)
    print(f"Candidato: {CANDIDATE_DIR}")
    print(f"Destino: {REFERENCE_DIR}")
    print(f"Revisões bloqueantes: {len(revisoes)}")
    print(f"Tickers 2025 no mapa: {len(mapa)}")
    print()

    resumo = promover_catalogo(
        candidate_dir=CANDIDATE_DIR,
        reference_dir=REFERENCE_DIR,
        contagens_esperadas=CONTAGENS,
        caminhos_protegidos=protegidos,
    )

    payload = {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "status": "APROVADO",
        "candidate_dir": str(CANDIDATE_DIR),
        "reference_dir": str(REFERENCE_DIR),
        **asdict(resumo),
    }
    RELATORIO.parent.mkdir(parents=True, exist_ok=True)
    RELATORIO.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("RESULTADO DA PROMOÇÃO")
    print("-" * 100)
    print(f"Instrumentos: {resumo.instrumentos:,}")
    print(f"Vigências de ticker: {resumo.tickers:,}")
    print(f"ISIN/identificadores: {resumo.identificadores:,}")
    print(f"Novos IDs: {resumo.novos_ids:,}")
    print(
        "Faixa de novos IDs: "
        f"{resumo.menor_novo_id}–{resumo.maior_novo_id}"
    )
    print("Bancos protegidos: inalterados por SHA-256")
    print(f"Relatório local: {RELATORIO}")
    print()
    print("RESULTADO: CATÁLOGO PROMOVIDO")
    print(
        "A carga histórica 2010–2023 continua bloqueada até a auditoria "
        "adversarial pós-promoção."
    )


if __name__ == "__main__":
    main()

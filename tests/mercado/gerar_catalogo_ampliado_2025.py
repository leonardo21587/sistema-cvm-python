from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.catalogo_ampliado import gerar_catalogo_ampliado  # noqa: E402


REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
REPORTS_DIR = ROOT_DIR / "data" / "market" / "reports"

INSTRUMENTOS_ATUAIS = REFERENCE_DIR / "instrumentos.csv"
GRUPOS_2025 = REPORTS_DIR / "universo_2025_reconciliado_grupos.csv"

SAIDA_CATALOGO = REPORTS_DIR / "catalogo_ampliado_instrumentos_2025.csv"
SAIDA_ALOCACOES = REPORTS_DIR / "catalogo_ampliado_alocacoes_2025.csv"
SAIDA_REVISAO = REPORTS_DIR / "catalogo_ampliado_revisao_2025.csv"


def _ler(caminho: Path, *, delimitador: str) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=delimitador))


def _escrever(
    caminho: Path,
    linhas: list[dict[str, str]],
    campos: list[str],
    *,
    delimitador: str,
) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=campos,
            delimiter=delimitador,
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def main() -> None:
    instrumentos = _ler(INSTRUMENTOS_ATUAIS, delimitador=",")
    grupos = _ler(GRUPOS_2025, delimitador=";")

    resultado = gerar_catalogo_ampliado(
        instrumentos,
        grupos,
    )

    _escrever(
        SAIDA_CATALOGO,
        resultado.instrumentos,
        [
            "INSTRUMENTO_ID",
            "CD_CVM",
            "TIPO_ATIVO",
            "CLASSE",
            "MOEDA",
            "DT_INICIO",
            "DT_FIM",
            "STATUS",
            "FONTE",
        ],
        delimitador=",",
    )
    _escrever(
        SAIDA_ALOCACOES,
        resultado.alocacoes,
        [
            "CHAVE_CANDIDATO",
            "INSTRUMENTO_ID",
            "ORIGEM_ID",
            "CD_CVM",
            "TIPO_ATIVO",
            "CLASSE",
            "PRIMEIRA_DATA_2025",
            "ULTIMA_DATA_2025",
            "TICKERS_2025",
            "ISINS_2025",
        ],
        delimitador=";",
    )
    _escrever(
        SAIDA_REVISAO,
        resultado.revisao,
        ["NIVEL", "CHAVE", "DETALHE"],
        delimitador=";",
    )

    reutilizados = sum(
        1 for x in resultado.alocacoes
        if x["ORIGEM_ID"] == "REUTILIZADO"
    )
    novos = sum(
        1 for x in resultado.alocacoes
        if x["ORIGEM_ID"] == "NOVO"
    )
    maior_antigo = max(
        int(x["INSTRUMENTO_ID"]) for x in instrumentos
    )
    maior_final = max(
        int(x["INSTRUMENTO_ID"]) for x in resultado.instrumentos
    )

    print("=" * 96)
    print("SISTEMA CVM — D.4 — CATÁLOGO AMPLIADO DE INSTRUMENTOS — PRÉ-PROMOÇÃO")
    print("=" * 96)
    print(f"Instrumentos existentes preservados: {len(instrumentos):,}")
    print(f"Grupos candidatos recebidos: {len(grupos):,}")
    print(f"IDs existentes reutilizados: {reutilizados:,}")
    print(f"Novos INSTRUMENTO_ID: {novos:,}")
    print(f"Instrumentos no catálogo candidato: {len(resultado.instrumentos):,}")
    print(f"Maior ID antes: {maior_antigo:,}")
    print(f"Maior ID candidato: {maior_final:,}")
    print(f"Pendências/revisões: {len(resultado.revisao):,}")
    print(f"GATE_APROVADO: {resultado.gate_aprovado}")
    print()

    print(f"Catálogo candidato: {SAIDA_CATALOGO}")
    print(f"Mapa de alocações: {SAIDA_ALOCACOES}")
    print(f"Revisão: {SAIDA_REVISAO}")
    print()

    if resultado.gate_aprovado:
        print("RESULTADO: APROVADO PARA A PRÓXIMA SUBETAPA")
        print(
            "Nenhum arquivo de referência foi sobrescrito. "
            "A promoção permanece separada do gate."
        )
    else:
        print("RESULTADO: BLOQUEADO")
        print(
            "Não promover o catálogo e não iniciar a carga histórica "
            "enquanto houver revisão."
        )


if __name__ == "__main__":
    main()

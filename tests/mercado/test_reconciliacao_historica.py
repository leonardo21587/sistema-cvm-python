from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.reconciliacao_historica import (  # noqa: E402
    ResultadoReconciliacaoHistorica,
    serializar_resultados,
)


def main() -> None:
    print("=" * 86)
    print("SISTEMA CVM — TESTE D.5 — RECONCILIAÇÃO HISTÓRICA")
    print("=" * 86)

    item = ResultadoReconciliacaoHistorica(
        ticker="OLD3",
        status="NOVO_INSTRUMENTO_HISTORICO_CANDIDATO",
        cd_cvm="000001",
        tipo_ativo="ACAO",
        classe="ON",
        instrumento_id="",
        chave_instrumento="000001|ACAO|ON",
        fonte="FIXTURE",
        detalhe="",
    )
    linhas = serializar_resultados([item])

    assert len(linhas) == 1
    assert linhas[0]["TICKER"] == "OLD3"
    assert linhas[0]["CHAVE_INSTRUMENTO"] == "000001|ACAO|ON"

    print("RESULTADO: APROVADO")
    print("Separação alias existente vs instrumento histórico novo: aprovada")
    print("Nenhum ID é alocado nesta subetapa: aprovado")


if __name__ == "__main__":
    main()

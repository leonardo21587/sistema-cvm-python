from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.reconciliacao_catalogo import (  # noqa: E402
    EvidenciaVinculo,
    resolver_evidencias,
)


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.4 — RECONCILIAÇÃO DO CATÁLOGO")
    print("=" * 72)

    coerente = resolver_evidencias(
        "AXIA6",
        [
            EvidenciaVinculo(
                "AXIA6", "002437",
                "RESOLVIDO_EXCECAO_VALIDADA", "B3", 50,
            ),
            EvidenciaVinculo(
                "AXIA6", "002437",
                "RESOLVIDO", "COTAHIST", 10,
            ),
        ],
    )
    assert coerente.cd_cvm == "002437"
    assert coerente.status == "RESOLVIDO_EXCECAO_VALIDADA"
    assert coerente.conflito is None

    conflito = resolver_evidencias(
        "TEST3",
        [
            EvidenciaVinculo(
                "TEST3", "000001", "RESOLVIDO", "A", 10,
            ),
            EvidenciaVinculo(
                "TEST3", "000002", "RESOLVIDO", "B", 20,
            ),
        ],
    )
    assert conflito.status == "CONFLITO"
    assert conflito.cd_cvm is None

    fora = resolver_evidencias(
        "PPLA11",
        [
            EvidenciaVinculo(
                "PPLA11", "080152",
                "FORA_UNIVERSO_SISTEMA", "CVM", 50,
            )
        ],
    )
    assert fora.status == "FORA_UNIVERSO_SISTEMA"
    assert fora.cd_cvm == "080152"

    print("RESULTADO: APROVADO")
    print("evidências coerentes: consolidadas")
    print("CD_CVM divergente: bloqueado")
    print("fora do universo: preservado explicitamente")


if __name__ == "__main__":
    main()

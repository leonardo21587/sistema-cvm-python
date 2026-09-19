from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.providers.b3_companhias import (  # noqa: E402
    _normalizar_cd_cvm,
    _normalizar_cnpj,
    _payload_b64,
)


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.4 — PROVIDER B3 COMPANHIAS")
    print("=" * 72)

    assert _normalizar_cd_cvm("2437") == "002437"
    assert _normalizar_cd_cvm("002437") == "002437"
    assert _normalizar_cnpj("00.001.180/0001-26") == "00001180000126"

    payload = _payload_b64({
        "codeCVM": "002437",
        "language": "pt-br",
    })
    assert isinstance(payload, str)
    assert payload

    print("RESULTADO: APROVADO")
    print("normalização CD_CVM: aprovada")
    print("normalização CNPJ: aprovada")
    print("payload base64 B3: aprovado")


if __name__ == "__main__":
    main()

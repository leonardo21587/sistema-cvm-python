from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.providers.cvm_fca import FcaValorMobiliario  # noqa: E402
from src.mercado.reconciliacao_nome_fca_historica import (  # noqa: E402
    candidatos_nome_fca,
    indexar_companhias_fca,
)


def _registro(cd: str, nome: str) -> FcaValorMobiliario:
    return FcaValorMobiliario(
        cd_cvm=cd,
        cnpj="00000000000000",
        data_referencia=date(2020, 1, 1),
        versao=1,
        id_documento="1",
        nome_empresarial=nome,
        valor_mobiliario="Ações",
        sigla_classe_preferencial="",
        classe_preferencial="",
        codigo_negociacao="",
        composicao_bdr_unit="",
        mercado="",
        sigla_entidade_administradora="",
        entidade_administradora="",
        data_inicio_negociacao=None,
        data_fim_negociacao=None,
        segmento="",
        data_inicio_listagem=None,
        data_fim_listagem=None,
    )


def main() -> None:
    print("=" * 90)
    print("SISTEMA CVM — TESTE D.5 — PONTE NOME B3/FCA")
    print("=" * 90)

    indice = indexar_companhias_fca(
        [
            _registro("000001", "BR Properties S.A."),
            _registro("000002", "Companhia Exemplo de Energia S.A."),
        ]
    )

    c1 = candidatos_nome_fca(
        nome_b3="BR PROPERT",
        nomes_por_cd=indice,
    )
    assert len(c1) == 1
    assert c1[0].cd_cvm == "000001"

    c2 = candidatos_nome_fca(
        nome_b3="EXEMPLO ENERG",
        nomes_por_cd=indice,
    )
    assert len(c2) == 1
    assert c2[0].cd_cvm == "000002"

    print("RESULTADO: APROVADO")
    print("Prefixo abreviado B3: aprovado")
    print("Match por tokens significativos: aprovado")
    print("Saída permanece candidata: aprovado")


if __name__ == "__main__":
    main()

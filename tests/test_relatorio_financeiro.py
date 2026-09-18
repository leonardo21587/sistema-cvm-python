from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from src.relatorio_financeiro import (  # noqa: E402
    gerar_relatorio_financeiro,
)


CD_CVM_ITAU = "019348"

ANOS = [
    2023,
    2024,
    2025,
]


def main() -> None:
    print("=" * 78)
    print("SISTEMA CVM — TESTE RELATÓRIO FINANCEIRO — ETAPA B.4")
    print("=" * 78)

    relatorio = gerar_relatorio_financeiro(
        CD_CVM_ITAU,
        "ITAU UNIBANCO HOLDING S.A.",
        ANOS,
    )

    obrigatorias = {
        "STATUS_VALIDACAO",
        "ANOS",
        "RESUMO_EXECUTIVO",
        "ANALISE_INDICADORES",
        "SINTESES_GRUPOS",
        "PRINCIPAIS_MUDANCAS",
        "PONTOS_ATENCAO",
        "CONCLUSAO",
        "VALIDACAO",
        "DUPONT",
        "INDICADORES_SETORIAIS",
        "METODOLOGIA",
    }

    faltantes = (
        obrigatorias
        - set(
            relatorio.keys()
        )
    )

    assert not faltantes, (
        "Chaves ausentes: "
        f"{sorted(faltantes)}"
    )

    analise = relatorio[
        "ANALISE_INDICADORES"
    ]

    assert len(
        analise
    ) == 9, (
        "Esperados 9 indicadores na análise."
    )

    codigos = set(
        analise[
            "INDICADOR"
        ]
    )

    esperados = {
        "CAP_CONTABIL",
        "PF_ATIVO",
        "CRESC_ATIVO",
        "CRESC_PL",
        "CRESC_LL",
        "RBI_ATIVO_MEDIO",
        "PRETRIB_ATIVO_MEDIO",
        "ROA",
        "ROE",
    }

    assert codigos == esperados, (
        "Conjunto de indicadores divergente."
    )

    proibidos = {
        "IPL",
        "PCT",
        "CE",
        "EFSAT",
        "LG",
        "LC",
        "LS",
        "ICJ",
        "GA",
        "RSV",
    }

    assert not (
        codigos
        & proibidos
    ), (
        "Indicadores tradicionais incompatíveis "
        "entraram no relatório setorial."
    )

    quadro = (
        analise
        .set_index(
            "INDICADOR"
        )
    )

    benchmarks = {
        "CAP_CONTABIL": 0.0701,
        "PF_ATIVO": 0.7900,
        "CRESC_ATIVO": 0.0742,
        "CRESC_PL": -0.0281,
        "CRESC_LL": 0.0883,
        "RBI_ATIVO_MEDIO": 0.0469,
        "PRETRIB_ATIVO_MEDIO": 0.0170,
        "ROA": 0.015488,
        "ROE": 0.234815,
    }

    tolerancias = {
        "CAP_CONTABIL": 0.0002,
        "PF_ATIVO": 0.0002,
        "CRESC_ATIVO": 0.0002,
        "CRESC_PL": 0.0002,
        "CRESC_LL": 0.0002,
        "RBI_ATIVO_MEDIO": 0.0002,
        "PRETRIB_ATIVO_MEDIO": 0.0002,
        "ROA": 0.00005,
        "ROE": 0.00005,
    }

    for codigo, esperado in benchmarks.items():
        encontrado = float(
            quadro.loc[
                codigo,
                "RECENTE",
            ]
        )

        assert abs(
            encontrado
            - esperado
        ) <= tolerancias[
            codigo
        ], (
            f"{codigo}: esperado aproximadamente "
            f"{esperado}, encontrado {encontrado}."
        )

    grupos = set(
        relatorio[
            "SINTESES_GRUPOS"
        ].keys()
    )

    assert grupos == {
        "Capitalização e Funding",
        "Crescimento",
        "Intermediação e Rentabilidade",
    }

    assert (
        "nove indicadores"
        in relatorio[
            "RESUMO_EXECUTIVO"
        ]
    )

    assert (
        "DuPont"
        not in relatorio[
            "RESUMO_EXECUTIVO"
        ]
    )

    assert (
        isinstance(
            relatorio[
                "DUPONT"
            ],
            pd.DataFrame,
        )
        and relatorio[
            "DUPONT"
        ].empty
    )

    print()
    print(
        "STATUS:",
        relatorio[
            "STATUS_VALIDACAO"
        ],
    )

    print()
    print(
        "RESUMO EXECUTIVO"
    )
    print("-" * 78)
    print(
        relatorio[
            "RESUMO_EXECUTIVO"
        ]
    )

    print()
    print(
        "INDICADORES — EXERCÍCIO RECENTE"
    )
    print("-" * 78)

    print(
        analise[
            [
                "INDICADOR",
                "RECENTE",
                "DELTA",
                "TRAJETORIA",
                "STATUS_RECENTE",
            ]
        ].to_string(
            index=False
        )
    )

    print()
    print(
        "RESULTADO: APROVADO — relatório setorial "
        "financeiro contém apenas os 9 indicadores "
        "metodologicamente aplicáveis."
    )
    print(
        "Nenhuma integração com app.py foi realizada nesta etapa."
    )


if __name__ == "__main__":
    main()

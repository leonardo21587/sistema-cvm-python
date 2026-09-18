from __future__ import annotations

"""
Teste de regressão da primeira camada de indicadores FINANCEIRA.

Este teste NÃO altera o banco nem o aplicativo.
Ele compara a implementação com os benchmarks obtidos na ETAPA A.3.
"""

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from src.banco import conectar  # noqa: E402
from src.indicadores_financeiros import (  # noqa: E402
    INDICADORES_FINANCEIROS,
    calcular_indicadores_financeiros,
)
from src.layouts_cvm import (  # noqa: E402
    LAYOUT_FINANCEIRA,
    detectar_layout,
)


ANOS = [2023, 2024, 2025]


def identificar_pares_financeiros() -> pd.DataFrame:
    con = conectar(
        read_only=True
    )

    try:
        base = con.execute(
            """
            SELECT
                CD_CVM,
                DENOM_CIA,
                ANO,
                DEMONSTRACAO,
                CD_CONTA,
                DS_CONTA
            FROM dfp
            WHERE ANO BETWEEN 2023 AND 2025
              AND DEMONSTRACAO IN ('BPP', 'DRE')
            ORDER BY CD_CVM, ANO, DEMONSTRACAO, CD_CONTA
            """
        ).fetchdf()

    finally:
        con.close()

    base["CD_CVM"] = (
        base["CD_CVM"]
        .astype(str)
        .str.zfill(6)
    )

    linhas = []

    for (
        cd_cvm,
        ano,
    ), g in base.groupby(
        [
            "CD_CVM",
            "ANO",
        ]
    ):
        bpp = g[
            g["DEMONSTRACAO"]
            .eq("BPP")
        ][
            [
                "CD_CONTA",
                "DS_CONTA",
            ]
        ]

        dre = g[
            g["DEMONSTRACAO"]
            .eq("DRE")
        ][
            [
                "CD_CONTA",
                "DS_CONTA",
            ]
        ]

        layout = detectar_layout(
            bpp,
            dre,
        )

        if (
            layout.codigo
            == LAYOUT_FINANCEIRA
        ):
            nome = (
                g["DENOM_CIA"]
                .dropna()
                .astype(str)
                .iloc[0]
            )

            linhas.append(
                {
                    "CD_CVM": cd_cvm,
                    "DENOM_CIA": nome,
                    "ANO": int(ano),
                }
            )

    return pd.DataFrame(
        linhas
    )


def main() -> None:
    print(
        "="
        * 78
    )
    print(
        "SISTEMA CVM — TESTE INDICADORES FINANCEIROS — ETAPA B.1"
    )
    print(
        "="
        * 78
    )
    print()

    pares = identificar_pares_financeiros()

    assert len(pares) == 51, (
        "Benchmark A.3 esperado: 51 empresa-anos FINANCEIRA. "
        f"Encontrado: {len(pares)}."
    )

    empresas = (
        pares[
            "CD_CVM"
        ]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    assert len(empresas) == 21, (
        "Benchmark esperado: 21 companhias FINANCEIRA. "
        f"Encontrado: {len(empresas)}."
    )

    partes = []

    for cd_cvm in empresas:
        dados = calcular_indicadores_financeiros(
            cd_cvm,
            ANOS,
        )

        if not dados.empty:
            partes.append(
                dados
            )

    resultado = pd.concat(
        partes,
        ignore_index=True,
    )

    esperado_linhas = (
        51
        * len(
            INDICADORES_FINANCEIROS
        )
    )

    assert len(resultado) == esperado_linhas, (
        f"Esperadas {esperado_linhas} linhas "
        f"(51 empresa-anos × {len(INDICADORES_FINANCEIROS)} indicadores), "
        f"encontradas {len(resultado)}."
    )

    duplicadas = resultado.duplicated(
        subset=[
            "CD_CVM",
            "ANO",
            "INDICADOR",
        ],
        keep=False,
    )

    assert not duplicadas.any(), (
        "Há duplicidade de empresa-ano-indicador."
    )

    status_invalidos = (
        set(
            resultado[
                "STATUS"
            ].unique()
        )
        - {
            "OK",
            "N/D",
            "N/A",
        }
    )

    assert not status_invalidos, (
        "STATUS inesperados: "
        f"{sorted(status_invalidos)}"
    )

    resumo = (
        resultado.groupby(
            [
                "INDICADOR",
                "STATUS",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size": "N",
            }
        )
    )

    print(
        "RESUMO DE STATUS"
    )
    print(
        "-"
        * 78
    )
    print(
        resumo.to_string(
            index=False
        )
    )
    print()

    benchmarks_ok = {
        "CAP_CONTABIL": 50,
        "PF_ATIVO": 50,
        "CRESC_ATIVO": 29,
        "CRESC_PL": 29,
        "CRESC_LL": 29,
        "RBI_ATIVO_MEDIO": 50,
        "PRETRIB_ATIVO_MEDIO": 50,
    }

    divergencias = []

    for codigo, esperado in benchmarks_ok.items():
        encontrado = int(
            (
                resultado[
                    "INDICADOR"
                ].eq(
                    codigo
                )
                & resultado[
                    "STATUS"
                ].eq(
                    "OK"
                )
            )
            .sum()
        )

        if encontrado != esperado:
            divergencias.append(
                {
                    "INDICADOR": codigo,
                    "OK_ESPERADO_A3": esperado,
                    "OK_ENCONTRADO": encontrado,
                }
            )

    if divergencias:
        print(
            "DIVERGÊNCIAS CONTRA A ETAPA A.3"
        )
        print(
            "-"
            * 78
        )
        print(
            pd.DataFrame(
                divergencias
            ).to_string(
                index=False
            )
        )
        print()

        raise AssertionError(
            "A implementação B.1 divergiu dos benchmarks da A.3."
        )

    # 2023 deve ser base e, portanto, os três indicadores
    # de crescimento não podem aparecer como OK.
    crescimento_2023 = resultado[
        resultado[
            "ANO"
        ].eq(2023)
        & resultado[
            "INDICADOR"
        ].isin(
            [
                "CRESC_ATIVO",
                "CRESC_PL",
                "CRESC_LL",
            ]
        )
    ]

    assert not crescimento_2023[
        "STATUS"
    ].eq(
        "OK"
    ).any(), (
        "Indicador de crescimento calculado indevidamente em 2023."
    )

    # Nenhum NaN pode ser rotulado como OK.
    ok_sem_valor = resultado[
        resultado[
            "STATUS"
        ].eq("OK")
        & resultado[
            "VALOR"
        ].isna()
    ]

    assert ok_sem_valor.empty, (
        "Há linhas STATUS=OK sem valor numérico."
    )

    # Toda linha não OK deve explicar o motivo.
    nao_ok_sem_motivo = resultado[
        ~resultado[
            "STATUS"
        ].eq("OK")
        & (
            resultado[
                "MOTIVO"
            ].isna()
            | resultado[
                "MOTIVO"
            ]
            .astype(str)
            .str.strip()
            .eq("")
        )
    ]

    assert nao_ok_sem_motivo.empty, (
        "Há linhas N/D ou N/A sem justificativa."
    )

    print(
        "BENCHMARKS A.3"
    )
    print(
        "-"
        * 78
    )

    for codigo, esperado in benchmarks_ok.items():
        print(
            f"{codigo:25s} OK = {esperado}"
        )

    print()
    print(
        "RESULTADO: APROVADO — implementação B.1 reproduz "
        "os benchmarks da auditoria A.3."
    )
    print(
        "Nenhuma integração com app.py foi realizada."
    )


if __name__ == "__main__":
    main()

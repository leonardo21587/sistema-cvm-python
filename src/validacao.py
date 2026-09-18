from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from config.settings import PROCESSED_DIR
from src.analise_horizontal import calcular_analise_horizontal
from src.analise_vertical import calcular_analise_vertical
from src.banco import anos_disponiveis, carregar_demonstracao
from src.indicadores import (
    FORMULAS,
    calcular_indicadores,
    validar_dupont,
)
from src.layouts_cvm import (
    LAYOUT_FINANCEIRA,
    LAYOUT_PADRAO,
    detectar_layout,
    normalizar_descricao,
)


ARQUIVO_AUXILIAR = (
    PROCESSED_DIR
    / "saldos_auxiliares_2022.parquet"
)


STATUS_ORDEM = {
    "OK": 0,
    "INFO": 1,
    "ALERTA": 2,
    "BLOQUEIO": 3,
}


CONTAS_INDICADORES_PADRAO = {
    "BPA": {
        "1",
        "1.01",
        "1.01.01",
        "1.01.02",
        "1.01.03",
        "1.02.01",
        "1.02.02",
        "1.02.03",
        "1.02.04",
    },
    "BPP": {
        "2",
        "2.01",
        "2.01.04",
        "2.02",
        "2.02.01",
        "2.03",
    },
    "DRE": {
        "3.01",
        "3.05",
        "3.06.02",
        "3.11",
    },
}


def _normalizar_cd_cvm(
    cd_cvm: str,
) -> str:
    return (
        str(cd_cvm)
        .strip()
        .zfill(6)
    )


def _linha(
    categoria: str,
    teste: str,
    status: str,
    detalhe: str,
    ano: int | None = None,
) -> dict[str, object]:
    return {
        "CATEGORIA": categoria,
        "ANO": ano,
        "TESTE": teste,
        "STATUS": status,
        "DETALHE": detalhe,
    }


def _valor_conta(
    df: pd.DataFrame,
    codigo: str,
) -> float | None:
    linhas = df[
        df["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq(codigo)
    ]

    if linhas.empty:
        return None

    if len(linhas) != 1:
        return None

    valor = (
        linhas.iloc[0][
            "VL_CONTA"
        ]
    )

    if pd.isna(valor):
        return None

    return float(valor)


def _quase_igual(
    a: float,
    b: float,
    tolerancia_abs: float = 1.0,
    tolerancia_rel: float = 1e-8,
) -> bool:
    tolerancia = max(
        tolerancia_abs,
        tolerancia_rel
        * max(
            abs(a),
            abs(b),
            1.0,
        ),
    )

    return (
        abs(a - b)
        <= tolerancia
    )


def _validar_unicidade(
    df: pd.DataFrame,
    demonstracao: str,
    ano: int,
) -> dict[str, object]:
    duplicadas = int(
        df["CD_CONTA"]
        .astype(str)
        .duplicated(
            keep=False
        )
        .sum()
    )

    if duplicadas == 0:
        return _linha(
            "Integridade",
            f"Unicidade {demonstracao}",
            "OK",
            "Uma observação por código de conta.",
            ano,
        )

    return _linha(
        "Integridade",
        f"Unicidade {demonstracao}",
        "BLOQUEIO",
        (
            f"{duplicadas} linhas pertencem "
            "a códigos de conta duplicados."
        ),
        ano,
    )


def _validar_escala(
    df: pd.DataFrame,
    demonstracao: str,
    ano: int,
) -> dict[str, object]:
    if (
        "UNIDADE_SISTEMA"
        not in df.columns
    ):
        return _linha(
            "Integridade",
            f"Escala {demonstracao}",
            "BLOQUEIO",
            "Coluna UNIDADE_SISTEMA ausente.",
            ano,
        )

    unidades = sorted(
        set(
            df["UNIDADE_SISTEMA"]
            .dropna()
            .astype(str)
            .str.strip()
        )
    )

    if unidades == ["R$ mil"]:
        return _linha(
            "Integridade",
            f"Escala {demonstracao}",
            "OK",
            "Todos os valores estão em R$ mil.",
            ano,
        )

    return _linha(
        "Integridade",
        f"Escala {demonstracao}",
        "BLOQUEIO",
        f"Unidades encontradas: {unidades}",
        ano,
    )


def _validar_bp(
    bpa: pd.DataFrame,
    bpp: pd.DataFrame,
    ano: int,
) -> dict[str, object]:
    ativo = _valor_conta(
        bpa,
        "1",
    )

    passivo = _valor_conta(
        bpp,
        "2",
    )

    if (
        ativo is None
        or passivo is None
    ):
        return _linha(
            "Reconciliação",
            "Ativo Total = Passivo Total",
            "BLOQUEIO",
            "Conta 1 ou conta 2 ausente.",
            ano,
        )

    diferenca = (
        ativo
        - passivo
    )

    if _quase_igual(
        ativo,
        passivo,
    ):
        return _linha(
            "Reconciliação",
            "Ativo Total = Passivo Total",
            "OK",
            (
                f"Ativo={ativo:.2f}; "
                f"Passivo={passivo:.2f}; "
                f"diferença={diferenca:.2f}."
            ),
            ano,
        )

    return _linha(
        "Reconciliação",
        "Ativo Total = Passivo Total",
        "BLOQUEIO",
        (
            f"Ativo={ativo:.2f}; "
            f"Passivo={passivo:.2f}; "
            f"diferença={diferenca:.2f}."
        ),
        ano,
    )


def _validar_identidades_dre(
    dre: pd.DataFrame,
    ano: int,
    layout_codigo: str,
) -> list[dict[str, object]]:
    testes = [
        (
            "3.03 = 3.01 + 3.02",
            "3.03",
            [
                "3.01",
                "3.02",
            ],
        ),
        (
            "3.05 = 3.03 + 3.04",
            "3.05",
            [
                "3.03",
                "3.04",
            ],
        ),
        (
            "3.07 = 3.05 + 3.06",
            "3.07",
            [
                "3.05",
                "3.06",
            ],
        ),
        (
            "3.09 = 3.07 + 3.08",
            "3.09",
            [
                "3.07",
                "3.08",
            ],
        ),
        (
            "3.11 = 3.09 + 3.10",
            "3.11",
            [
                "3.09",
                "3.10",
            ],
        ),
    ]

    if (
        layout_codigo
        != LAYOUT_PADRAO
    ):
        return [
            _linha(
                "Reconciliação DRE",
                nome,
                "INFO",
                (
                    "Reconciliação estrutural padrão "
                    "não aplicada ao layout setorial."
                ),
                ano,
            )
            for (
                nome,
                _subtotal,
                _componentes,
            )
            in testes
        ]

    saida = []

    for (
        nome,
        subtotal,
        componentes,
    ) in testes:
        v_subtotal = _valor_conta(
            dre,
            subtotal,
        )

        valores = [
            _valor_conta(
                dre,
                codigo,
            )
            for codigo
            in componentes
        ]

        if (
            v_subtotal is None
            or any(
                valor is None
                for valor
                in valores
            )
        ):
            saida.append(
                _linha(
                    "Reconciliação DRE",
                    nome,
                    "INFO",
                    (
                        "Verificação não aplicável: "
                        "uma ou mais contas não foram publicadas."
                    ),
                    ano,
                )
            )
            continue

        calculado = float(
            sum(valores)
        )

        diferenca = (
            v_subtotal
            - calculado
        )

        status = (
            "OK"
            if _quase_igual(
                v_subtotal,
                calculado,
            )
            else "ALERTA"
        )

        saida.append(
            _linha(
                "Reconciliação DRE",
                nome,
                status,
                (
                    f"Publicado={v_subtotal:.2f}; "
                    f"calculado={calculado:.2f}; "
                    f"diferença={diferenca:.2f}."
                ),
                ano,
            )
        )

    return saida


def _contas_requeridas_layout(
    demonstracao: str,
    layout,
) -> set[str]:
    if (
        layout.codigo
        == LAYOUT_PADRAO
    ):
        return set(
            CONTAS_INDICADORES_PADRAO[
                demonstracao
            ]
        )

    if demonstracao == "BPA":
        return {"1"}

    if demonstracao == "BPP":
        requeridas = {"2"}

        if (
            layout.codigo_pl
            is not None
        ):
            requeridas.add(
                str(
                    layout.codigo_pl
                )
            )

        return requeridas

    if demonstracao == "DRE":
        if (
            layout.codigo_ll
            is None
        ):
            return set()

        return {
            str(
                layout.codigo_ll
            )
        }

    return set()


def _validar_contas_indicadores(
    demonstracao: str,
    df: pd.DataFrame,
    ano: int,
    layout,
) -> dict[str, object]:
    publicadas = set(
        df["CD_CONTA"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    requeridas = (
        _contas_requeridas_layout(
            demonstracao,
            layout,
        )
    )

    faltantes = sorted(
        requeridas
        - publicadas
    )

    if not faltantes:
        if (
            layout.codigo
            == LAYOUT_PADRAO
        ):
            detalhe = (
                "Todas as contas mapeadas para "
                "indicadores estão disponíveis."
            )
        else:
            detalhe = (
                "Contas necessárias aos indicadores "
                "aplicáveis ao layout setorial "
                "estão disponíveis."
            )

        return _linha(
            "Indicadores",
            f"Contas necessárias {demonstracao}",
            "OK",
            detalhe,
            ano,
        )

    return _linha(
        "Indicadores",
        f"Contas necessárias {demonstracao}",
        "ALERTA",
        (
            "Contas ausentes: "
            + ", ".join(
                faltantes
            )
        ),
        ano,
    )


def _validar_av(
    cd_cvm: str,
    demonstracao: str,
    ano: int,
    layout,
) -> dict[str, object]:
    if (
        demonstracao == "DRE"
        and layout.codigo == LAYOUT_FINANCEIRA
    ):
        return _linha(
            "AV",
            f"Base AV {demonstracao}",
            "INFO",
            (
                "Análise vertical da DRE = N/A para o layout "
                "FINANCEIRA; a estrutura setorial não utiliza "
                "Receita Líquida tradicional como base."
            ),
            ano,
        )

    av = calcular_analise_vertical(
        cd_cvm,
        demonstracao,
        anos=[
            ano
        ],
    )

    conta_base = {
        "BPA": "1",
        "BPP": "2",
        "DRE": "3.01",
    }[
        demonstracao
    ]

    linha_base = av[
        av["CD_CONTA"]
        .astype(str)
        .eq(
            conta_base
        )
    ]

    coluna = (
        f"AV_{ano}"
    )

    if (
        len(linha_base) != 1
        or coluna
        not in av.columns
        or pd.isna(
            linha_base.iloc[0][
                coluna
            ]
        )
    ):
        if (
            demonstracao == "DRE"
            and layout.codigo != LAYOUT_PADRAO
        ):
            return _linha(
                "AV",
                f"Base AV {demonstracao}",
                "INFO",
                (
                    "Análise vertical da DRE não aplicada: "
                    "a conta-base 3.01 é ausente ou nula "
                    "neste layout setorial."
                ),
                ano,
            )

        return _linha(
            "AV",
            f"Base AV {demonstracao}",
            "BLOQUEIO",
            (
                f"Conta-base {conta_base} "
                "não pôde ser validada."
            ),
            ano,
        )

    valor = float(
        linha_base.iloc[0][
            coluna
        ]
    )

    if (
        abs(
            valor
            - 100.0
        )
        <= 1e-9
    ):
        return _linha(
            "AV",
            f"Base AV {demonstracao}",
            "OK",
            (
                f"Conta-base {conta_base} = 100%."
            ),
            ano,
        )

    return _linha(
        "AV",
        f"Base AV {demonstracao}",
        "BLOQUEIO",
        (
            f"Conta-base {conta_base} = "
            f"{valor:.12f}%, esperado 100%."
        ),
        ano,
    )


def _validar_ah(
    cd_cvm: str,
    demonstracao: str,
    anos: list[int],
) -> dict[str, object]:
    ano_base = min(
        anos
    )

    ah = calcular_analise_horizontal(
        cd_cvm,
        demonstracao,
        anos=anos,
        ano_base=ano_base,
    )

    if ah.empty:
        return _linha(
            "AH",
            f"Ano-base AH {demonstracao}",
            "BLOQUEIO",
            "Tabela AH vazia.",
            ano_base,
        )

    valores_base = pd.to_numeric(
        ah[
            ano_base
        ],
        errors="coerce",
    )

    mascara = (
        valores_base.notna()
        & valores_base.ne(0)
    )

    indice = pd.to_numeric(
        ah.loc[
            mascara,
            f"AH_IND_{ano_base}",
        ],
        errors="coerce",
    )

    variacao = pd.to_numeric(
        ah.loc[
            mascara,
            f"AH_VAR_{ano_base}",
        ],
        errors="coerce",
    )

    ok_indice = bool(
        (
            (
                indice
                - 100.0
            )
            .abs()
            <= 1e-9
        )
        .all()
    )

    ok_variacao = bool(
        (
            variacao
            .abs()
            <= 1e-9
        )
        .all()
    )

    if (
        ok_indice
        and ok_variacao
    ):
        return _linha(
            "AH",
            f"Ano-base AH {demonstracao}",
            "OK",
            (
                f"{int(mascara.sum())} contas "
                "com base não zero: "
                "índice=100 e variação=0."
            ),
            ano_base,
        )

    return _linha(
        "AH",
        f"Ano-base AH {demonstracao}",
        "BLOQUEIO",
        (
            "Existem contas com AH do ano-base "
            "diferente de 100/0."
        ),
        ano_base,
    )


def _validar_auxiliar(
    cd_cvm: str,
    primeiro_ano: int,
) -> dict[str, object]:
    if (
        primeiro_ano
        != 2023
    ):
        return _linha(
            "Médias",
            "Ano auxiliar",
            "INFO",
            (
                "A seleção não inicia em 2023; "
                "o ano anterior será obtido da "
                "base principal quando disponível."
            ),
            primeiro_ano,
        )

    if not ARQUIVO_AUXILIAR.exists():
        return _linha(
            "Médias",
            "Ano auxiliar 2022",
            "ALERTA",
            (
                "Arquivo "
                "saldos_auxiliares_2022.parquet ausente."
            ),
            2022,
        )

    d = pd.read_parquet(
        ARQUIVO_AUXILIAR
    )

    cd_cvm = (
        _normalizar_cd_cvm(
            cd_cvm
        )
    )

    empresa = d[
        d["CD_CVM"]
        .astype(str)
        .str.zfill(6)
        .eq(
            cd_cvm
        )
    ].copy()

    possui_at = bool(
        (
            (
                empresa[
                    "DEMONSTRACAO"
                ]
                == "BPA"
            )
            & (
                empresa[
                    "CD_CONTA"
                ]
                .astype(str)
                .str.strip()
                .eq("1")
            )
        )
        .any()
    )

    descricao_pl = (
        empresa["DS_CONTA"]
        .map(
            normalizar_descricao
        )
        if (
            "DS_CONTA"
            in empresa.columns
        )
        else pd.Series(
            dtype=str
        )
    )

    possui_pl = bool(
        (
            (
                empresa[
                    "DEMONSTRACAO"
                ]
                == "BPP"
            )
            & (
                descricao_pl.eq(
                    normalizar_descricao(
                        "Patrimônio Líquido Consolidado"
                    )
                )
            )
        )
        .any()
    )

    if (
        possui_at
        and possui_pl
    ):
        return _linha(
            "Médias",
            "Ano auxiliar 2022",
            "OK",
            (
                "Ativo Total e Patrimônio Líquido "
                "Consolidado de 2022 disponíveis."
            ),
            2022,
        )

    faltantes = []

    if not possui_at:
        faltantes.append(
            "Ativo Total"
        )

    if not possui_pl:
        faltantes.append(
            "Patrimônio Líquido Consolidado"
        )

    return _linha(
        "Médias",
        "Ano auxiliar 2022",
        "ALERTA",
        (
            "Saldo auxiliar ausente: "
            + ", ".join(
                faltantes
            )
            + ". Indicadores que usam médias "
            "de 2022/2023 podem ficar N/D."
        ),
        2022,
    )


def _validar_indicadores(
    cd_cvm: str,
    anos: list[int],
) -> list[dict[str, object]]:
    base = calcular_indicadores(
        cd_cvm,
        anos=anos,
    )

    saida = []

    esperados = len(
        FORMULAS
    )

    for ano in anos:
        d = base[
            base["ANO"]
            .eq(
                ano
            )
        ].copy()

        qtd = int(
            d[
                "INDICADOR"
            ]
            .nunique()
        )

        if (
            qtd
            == esperados
        ):
            saida.append(
                _linha(
                    "Indicadores",
                    "Quantidade de indicadores",
                    "OK",
                    (
                        f"{qtd} indicadores "
                        "calculados/representados."
                    ),
                    ano,
                )
            )
        else:
            saida.append(
                _linha(
                    "Indicadores",
                    "Quantidade de indicadores",
                    "BLOQUEIO",
                    (
                        f"{qtd} indicadores; "
                        f"esperado {esperados}."
                    ),
                    ano,
                )
            )

        if (
            "APLICABILIDADE"
            in d.columns
        ):
            na = (
                d[
                    d[
                        "APLICABILIDADE"
                    ]
                    .eq(
                        "NAO_APLICAVEL"
                    )
                ][
                    "INDICADOR"
                ]
                .tolist()
            )

            nd = (
                d[
                    d[
                        "APLICABILIDADE"
                    ]
                    .eq(
                        "APLICAVEL"
                    )
                    & d[
                        "VALOR"
                    ]
                    .isna()
                ][
                    "INDICADOR"
                ]
                .tolist()
            )
        else:
            na = []

            nd = (
                d[
                    d[
                        "VALOR"
                    ]
                    .isna()
                ][
                    "INDICADOR"
                ]
                .tolist()
            )

        if nd:
            saida.append(
                _linha(
                    "Indicadores",
                    "Cobertura dos indicadores",
                    "ALERTA",
                    (
                        "N/D entre indicadores "
                        "aplicáveis: "
                        + ", ".join(
                            nd
                        )
                    ),
                    ano,
                )
            )
        elif na:
            saida.append(
                _linha(
                    "Indicadores",
                    "Cobertura dos indicadores",
                    "INFO",
                    (
                        "N/A por metodologia do "
                        "layout setorial: "
                        + ", ".join(
                            na
                        )
                    ),
                    ano,
                )
            )
        else:
            saida.append(
                _linha(
                    "Indicadores",
                    "Cobertura dos indicadores",
                    "OK",
                    (
                        "Todos os indicadores "
                        "aplicáveis possuem "
                        "resultado numérico."
                    ),
                    ano,
                )
            )

    dupont = validar_dupont(
        cd_cvm,
        anos=anos,
    )

    for _, row in dupont.iterrows():
        ano = int(
            row[
                "ANO"
            ]
        )

        status_dupont = str(
            row[
                "STATUS"
            ]
        )

        if (
            status_dupont
            == "OK"
        ):
            status = "OK"

            detalhe = (
                f"ROA={float(row['ROA']):.12f}; "
                f"GA×RSV={float(row['GA_X_RSV']):.12f}; "
                f"diferença={float(row['DIFERENCA']):.12g}."
            )

        elif (
            status_dupont
            == "N/A"
        ):
            status = "INFO"

            detalhe = (
                "Validação DuPont não aplicável "
                "ao layout setorial."
            )

        elif (
            status_dupont
            == "N/D"
        ):
            status = "INFO"

            detalhe = (
                "Validação DuPont não aplicável "
                "por falta de dados."
            )

        else:
            status = "BLOQUEIO"

            detalhe = (
                f"ROA={row['ROA']}; "
                f"GA×RSV={row['GA_X_RSV']}; "
                f"diferença={row['DIFERENCA']}."
            )

        saida.append(
            _linha(
                "DuPont",
                "ROA = GA × RSV",
                status,
                detalhe,
                ano,
            )
        )

    return saida


def validar_empresa(
    cd_cvm: str,
    anos: list[int] | None = None,
) -> pd.DataFrame:
    cd_cvm = (
        _normalizar_cd_cvm(
            cd_cvm
        )
    )

    disponiveis = anos_disponiveis(
        cd_cvm
    )

    if anos is None:
        anos_usados = (
            disponiveis
        )
    else:
        anos_usados = sorted(
            int(
                ano
            )
            for ano in anos
            if int(
                ano
            )
            in disponiveis
        )

    if not anos_usados:
        raise ValueError(
            "Nenhum exercício disponível "
            f"para {cd_cvm}."
        )

    linhas = []

    linhas.append(
        _validar_auxiliar(
            cd_cvm,
            min(
                anos_usados
            ),
        )
    )

    for ano in anos_usados:
        demonstracoes = {}

        for dem in [
            "BPA",
            "BPP",
            "DRE",
        ]:
            demonstracoes[
                dem
            ] = carregar_demonstracao(
                cd_cvm,
                ano,
                dem,
            )

        bpa = (
            demonstracoes[
                "BPA"
            ]
        )

        bpp = (
            demonstracoes[
                "BPP"
            ]
        )

        dre = (
            demonstracoes[
                "DRE"
            ]
        )

        layout = detectar_layout(
            bpp,
            dre,
        )

        for dem in [
            "BPA",
            "BPP",
            "DRE",
        ]:
            d = (
                demonstracoes[
                    dem
                ]
            )

            if d.empty:
                linhas.append(
                    _linha(
                        "Integridade",
                        f"Existência {dem}",
                        "BLOQUEIO",
                        (
                            "Demonstração "
                            "não encontrada."
                        ),
                        ano,
                    )
                )
                continue

            linhas.append(
                _linha(
                    "Integridade",
                    f"Existência {dem}",
                    "OK",
                    (
                        f"{len(d)} contas "
                        "recuperadas."
                    ),
                    ano,
                )
            )

            linhas.append(
                _validar_unicidade(
                    d,
                    dem,
                    ano,
                )
            )

            linhas.append(
                _validar_escala(
                    d,
                    dem,
                    ano,
                )
            )

            linhas.append(
                _validar_contas_indicadores(
                    dem,
                    d,
                    ano,
                    layout,
                )
            )

            linhas.append(
                _validar_av(
                    cd_cvm,
                    dem,
                    ano,
                    layout,
                )
            )

        if (
            not bpa.empty
            and not bpp.empty
        ):
            linhas.append(
                _validar_bp(
                    bpa,
                    bpp,
                    ano,
                )
            )

        if not dre.empty:
            linhas.extend(
                _validar_identidades_dre(
                    dre,
                    ano,
                    layout.codigo,
                )
            )

    for dem in [
        "BPA",
        "BPP",
        "DRE",
    ]:
        linhas.append(
            _validar_ah(
                cd_cvm,
                dem,
                anos_usados,
            )
        )

    linhas.extend(
        _validar_indicadores(
            cd_cvm,
            anos_usados,
        )
    )

    resultado = pd.DataFrame(
        linhas
    )

    resultado[
        "ANO"
    ] = (
        pd.to_numeric(
            resultado[
                "ANO"
            ],
            errors="coerce",
        )
        .astype(
            "Int64"
        )
    )

    return resultado


def status_geral(
    validacao: pd.DataFrame,
) -> str:
    if validacao.empty:
        return "BLOQUEIO"

    pior = max(
        validacao[
            "STATUS"
        ]
        .map(
            STATUS_ORDEM
        )
    )

    inverso = {
        valor: chave
        for (
            chave,
            valor,
        )
        in STATUS_ORDEM.items()
    }

    return inverso[
        pior
    ]


def resumo_validacao(
    validacao: pd.DataFrame,
) -> pd.DataFrame:
    ordem = [
        "OK",
        "INFO",
        "ALERTA",
        "BLOQUEIO",
    ]

    contagem = (
        validacao[
            "STATUS"
        ]
        .value_counts()
        .reindex(
            ordem,
            fill_value=0,
        )
        .rename_axis(
            "STATUS"
        )
        .reset_index(
            name="QUANTIDADE"
        )
    )

    return contagem


def main() -> None:
    cd_cvm = "004170"
    anos = [
        2023,
        2024,
        2025,
    ]

    print(
        "=" * 70
    )

    print(
        "SISTEMA CVM - VALIDACAO"
    )

    print(
        "=" * 70
    )

    validacao = validar_empresa(
        cd_cvm,
        anos=anos,
    )

    print()
    print(
        validacao.to_string(
            index=False
        )
    )

    print()
    print(
        "RESUMO"
    )

    print(
        resumo_validacao(
            validacao
        ).to_string(
            index=False
        )
    )

    print()
    print(
        "STATUS GERAL:"
    )

    print(
        status_geral(
            validacao
        )
    )


if __name__ == "__main__":
    main()

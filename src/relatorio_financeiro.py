from __future__ import annotations

"""
Relatório setorial — instituições financeiras.

Módulo separado de src/relatorio.py para preservar integralmente
o relatório tradicional já aprovado.

Consome:
- 7 indicadores de src/indicadores_financeiros.py;
- ROA e ROE do motor original src/indicadores.py;
- validação original src/validacao.py.

Não recalcula BP/DRE e não cria substitutos para indicadores regulatórios.
"""

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from src.indicadores import quadro_indicadores  # noqa: E402
from src.indicadores_financeiros import (  # noqa: E402
    NOMES as NOMES_SETORIAIS,
    calcular_indicadores_financeiros,
)
from src.validacao import (  # noqa: E402
    status_geral,
    validar_empresa,
)


NOMES = {
    **NOMES_SETORIAIS,
    "ROA": "Retorno sobre o Ativo",
    "ROE": "Retorno sobre o Patrimônio Líquido",
}


GRUPOS = {
    "Capitalização e Funding": [
        "CAP_CONTABIL",
        "PF_ATIVO",
    ],
    "Crescimento": [
        "CRESC_ATIVO",
        "CRESC_PL",
        "CRESC_LL",
    ],
    "Intermediação e Rentabilidade": [
        "RBI_ATIVO_MEDIO",
        "PRETRIB_ATIVO_MEDIO",
        "ROA",
        "ROE",
    ],
}


ORDEM = [
    "CAP_CONTABIL",
    "PF_ATIVO",
    "CRESC_ATIVO",
    "CRESC_PL",
    "CRESC_LL",
    "RBI_ATIVO_MEDIO",
    "PRETRIB_ATIVO_MEDIO",
    "ROA",
    "ROE",
]


TOL_ABS = 0.0025
TOL_REL = 0.02


def _numero(valor) -> float | None:
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass

    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _fmt_pct(valor) -> str:
    valor = _numero(valor)

    if valor is None:
        return "N/D"

    return (
        f"{valor * 100:.2f}%"
        .replace(".", ",")
    )


def formatar_delta_pp(a, b) -> str:
    a = _numero(a)
    b = _numero(b)

    if a is None or b is None:
        return "N/D"

    delta = (
        b - a
    ) * 100

    sinal = (
        "+"
        if delta > 0
        else ""
    )

    numero = (
        f"{delta:.2f}"
        .replace(".", ",")
    )

    return f"{sinal}{numero} p.p."


def _tolerancia(
    referencia: float,
) -> float:
    return max(
        TOL_ABS,
        TOL_REL
        * abs(
            float(referencia)
        ),
    )


def _movimento(
    anterior,
    atual,
) -> str:
    anterior = _numero(
        anterior
    )
    atual = _numero(
        atual
    )

    if (
        anterior is None
        or atual is None
    ):
        return "N/D"

    delta = (
        atual
        - anterior
    )

    if abs(delta) <= _tolerancia(
        anterior
    ):
        return "→"

    return (
        "↑"
        if delta > 0
        else "↓"
    )


def _trajetoria_nivel(
    base,
    intermediario,
    recente,
) -> str:
    mov_1 = _movimento(
        base,
        intermediario,
    )

    mov_2 = _movimento(
        intermediario,
        recente,
    )

    mapa = {
        ("↑", "↑"): "trajetória crescente",
        ("↓", "↓"): "trajetória decrescente",
        ("↑", "↓"): "aumento seguido de redução",
        ("↓", "↑"): "redução seguida de recuperação",
        ("→", "→"): "praticamente estável",
        ("→", "↑"): "estabilidade seguida de aumento",
        ("↑", "→"): "aumento seguido de estabilidade",
        ("→", "↓"): "estabilidade seguida de redução",
        ("↓", "→"): "redução seguida de estabilidade",
    }

    if (
        mov_1 == "N/D"
        or mov_2 == "N/D"
    ):
        return "N/D"

    return mapa.get(
        (
            mov_1,
            mov_2,
        ),
        "comportamento misto",
    )


def _trajetoria_crescimento(
    intermediario,
    recente,
) -> str:
    intermediario = _numero(
        intermediario
    )
    recente = _numero(
        recente
    )

    if (
        intermediario is None
        or recente is None
    ):
        return "N/D"

    mov = _movimento(
        intermediario,
        recente,
    )

    if mov == "→":
        return "taxa de crescimento praticamente estável"

    if mov == "↑":
        return "aceleração da taxa de crescimento"

    return "desaceleração da taxa de crescimento"


def _valor_setorial(
    dados: pd.DataFrame,
    codigo: str,
    ano: int,
) -> tuple[
    float | None,
    str,
    str | None,
]:
    linhas = dados.loc[
        dados[
            "INDICADOR"
        ].eq(
            codigo
        )
        & dados[
            "ANO"
        ].eq(
            int(
                ano
            )
        )
    ]

    if linhas.empty:
        return (
            None,
            "N/D",
            "Exercício não disponível.",
        )

    linha = linhas.iloc[
        0
    ]

    return (
        _numero(
            linha[
                "VALOR"
            ]
        ),
        str(
            linha[
                "STATUS"
            ]
        ),
        (
            None
            if pd.isna(
                linha[
                    "MOTIVO"
                ]
            )
            else str(
                linha[
                    "MOTIVO"
                ]
            )
        ),
    )


def _valor_tradicional(
    quadro: pd.DataFrame,
    codigo: str,
    ano: int,
) -> tuple[
    float | None,
    str,
    str | None,
]:
    linhas = quadro.loc[
        quadro[
            "INDICADOR"
        ].eq(
            codigo
        )
    ]

    if linhas.empty:
        return (
            None,
            "N/D",
            "Indicador não encontrado no motor original.",
        )

    linha = linhas.iloc[
        0
    ]

    if str(
        linha.get(
            "APLICABILIDADE",
            "APLICAVEL",
        )
    ) != "APLICAVEL":
        return (
            None,
            "N/A",
            str(
                linha.get(
                    "MOTIVO_NA",
                    "Não aplicável ao layout setorial.",
                )
            ),
        )

    if ano not in linha.index:
        return (
            None,
            "N/D",
            "Exercício não disponível.",
        )

    valor = _numero(
        linha[
            ano
        ]
    )

    return (
        valor,
        (
            "OK"
            if valor is not None
            else "N/D"
        ),
        (
            None
            if valor is not None
            else "Valor não disponível."
        ),
    )


def _montar_base(
    cd_cvm: str,
    anos: list[int],
) -> pd.DataFrame:
    anos = sorted(
        {
            int(
                ano
            )
            for ano in anos
        }
    )

    setoriais = (
        calcular_indicadores_financeiros(
            cd_cvm,
            anos,
        )
    )

    tradicionais = (
        quadro_indicadores(
            cd_cvm,
            anos=anos,
        )
    )

    linhas = []

    for codigo in ORDEM:
        grupo = next(
            grupo
            for grupo, codigos
            in GRUPOS.items()
            if codigo in codigos
        )

        for ano in anos:
            if codigo in {
                "ROA",
                "ROE",
            }:
                valor, status, motivo = (
                    _valor_tradicional(
                        tradicionais,
                        codigo,
                        ano,
                    )
                )
            else:
                valor, status, motivo = (
                    _valor_setorial(
                        setoriais,
                        codigo,
                        ano,
                    )
                )

            linhas.append(
                {
                    "CD_CVM": str(
                        cd_cvm
                    ).zfill(
                        6
                    ),
                    "ANO": int(
                        ano
                    ),
                    "GRUPO": grupo,
                    "INDICADOR": codigo,
                    "NOME": NOMES[
                        codigo
                    ],
                    "UNIDADE": "%",
                    "VALOR": valor,
                    "STATUS": status,
                    "MOTIVO": motivo,
                }
            )

    return pd.DataFrame(
        linhas
    )


def _linha_analise(
    base_dados: pd.DataFrame,
    codigo: str,
    anos: list[int],
) -> dict[
    str,
    object,
]:
    anos = sorted(
        anos
    )

    ano_base = anos[
        0
    ]

    ano_recente = anos[
        -1
    ]

    ano_intermediario = (
        anos[
            1
        ]
        if len(
            anos
        ) >= 3
        else None
    )

    def obter(
        ano: int | None,
    ):
        if ano is None:
            return (
                None,
                "N/D",
                None,
            )

        linhas = (
            base_dados.loc[
                base_dados[
                    "INDICADOR"
                ].eq(
                    codigo
                )
                & base_dados[
                    "ANO"
                ].eq(
                    int(
                        ano
                    )
                )
            ]
        )

        if linhas.empty:
            return (
                None,
                "N/D",
                "Exercício não disponível.",
            )

        r = linhas.iloc[
            0
        ]

        return (
            _numero(
                r[
                    "VALOR"
                ]
            ),
            str(
                r[
                    "STATUS"
                ]
            ),
            r.get(
                "MOTIVO",
                None,
            ),
        )

    base, status_base, motivo_base = obter(
        ano_base
    )

    interm, status_inter, motivo_inter = obter(
        ano_intermediario
    )

    recente, status_rec, motivo_rec = obter(
        ano_recente
    )

    grupo = next(
        grupo
        for grupo, codigos
        in GRUPOS.items()
        if codigo in codigos
    )

    if codigo.startswith(
        "CRESC_"
    ):
        trajetoria = _trajetoria_crescimento(
            interm,
            recente,
        )

        delta = formatar_delta_pp(
            interm,
            recente,
        )

        if status_rec != "OK":
            interpretacao = (
                motivo_rec
                or "Taxa recente não disponível."
            )

        elif codigo == "CRESC_ATIVO":
            interpretacao = (
                f"O Ativo Total cresceu "
                f"{_fmt_pct(recente)} no exercício recente. "
                f"Em relação ao crescimento do exercício anterior, "
                f"houve {trajetoria}."
            )

        elif codigo == "CRESC_PL":
            interpretacao = (
                f"O Patrimônio Líquido apresentou variação de "
                f"{_fmt_pct(recente)} no exercício recente. "
                f"A comparação com a taxa anterior indica "
                f"{trajetoria}."
            )

        else:
            interpretacao = (
                f"O Lucro Líquido apresentou variação de "
                f"{_fmt_pct(recente)} no exercício recente. "
                f"A taxa percentual é exibida somente quando "
                f"a base anterior é positiva e comparável."
            )

        base_exibicao = None
        intermediario_exibicao = interm
        recente_exibicao = recente

    else:
        trajetoria = _trajetoria_nivel(
            base,
            interm,
            recente,
        )

        delta = formatar_delta_pp(
            base,
            recente,
        )

        if status_rec != "OK":
            interpretacao = (
                motivo_rec
                or "Indicador recente não disponível."
            )

        elif codigo == "CAP_CONTABIL":
            interpretacao = (
                f"A Capitalização Contábil encerrou o período "
                f"em {_fmt_pct(recente)} do Ativo Total. "
                f"O indicador mede capitalização contábil e "
                f"não representa capital regulatório ou Índice de Basileia."
            )

        elif codigo == "PF_ATIVO":
            interpretacao = (
                f"Os Passivos Financeiros representaram "
                f"{_fmt_pct(recente)} do Ativo Total no exercício recente. "
                f"A métrica descreve a composição contábil de funding "
                f"e deve ser interpretada em conjunto com a estrutura "
                f"específica da instituição."
            )

        elif codigo == "RBI_ATIVO_MEDIO":
            interpretacao = (
                f"O Resultado Bruto da Intermediação correspondeu a "
                f"{_fmt_pct(recente)} do Ativo Médio no exercício recente. "
                f"Essa razão não é denominada NIM, pois não utiliza "
                f"a definição prudencial/específica de margem financeira."
            )

        elif codigo == "PRETRIB_ATIVO_MEDIO":
            interpretacao = (
                f"O Resultado antes dos Tributos sobre o Lucro "
                f"correspondeu a {_fmt_pct(recente)} do Ativo Médio "
                f"no exercício recente, permitindo observar a "
                f"rentabilidade antes da tributação sobre o lucro."
            )

        elif codigo == "ROA":
            interpretacao = (
                f"O ROA encerrou o período em "
                f"{_fmt_pct(recente)}, medindo o resultado líquido "
                f"em relação ao Ativo Médio. A decomposição DuPont "
                f"tradicional não é aplicada ao layout financeiro."
            )

        elif codigo == "ROE":
            interpretacao = (
                f"O ROE encerrou o período em "
                f"{_fmt_pct(recente)}, medindo o retorno do resultado "
                f"líquido sobre o patrimônio conforme a metodologia "
                f"já validada no motor original."
            )

        else:
            interpretacao = (
                f"O indicador encerrou o período em "
                f"{_fmt_pct(recente)}."
            )

        base_exibicao = base
        intermediario_exibicao = interm
        recente_exibicao = recente

    status_recente = status_rec

    return {
        "GRUPO": grupo,
        "INDICADOR": codigo,
        "NOME": NOMES[
            codigo
        ],
        "BASE": base_exibicao,
        "INTERMEDIARIO": intermediario_exibicao,
        "RECENTE": recente_exibicao,
        "DELTA": delta,
        "TRAJETORIA": trajetoria,
        "INTERPRETACAO": interpretacao,
        "APLICABILIDADE": (
            "APLICAVEL"
            if status_recente
            != "N/A"
            else "NAO_APLICAVEL"
        ),
        "STATUS_RECENTE": status_recente,
        "MOTIVO_NA": (
            motivo_rec
            if status_recente
            == "N/A"
            else None
        ),
    }


def _principais_mudancas(
    analise: pd.DataFrame,
    limite: int = 3,
) -> list[
    str
]:
    candidatos = []

    for _, linha in analise.iterrows():
        codigo = str(
            linha[
                "INDICADOR"
            ]
        )

        if codigo.startswith(
            "CRESC_"
        ):
            referencia = _numero(
                linha[
                    "INTERMEDIARIO"
                ]
            )
            recente = _numero(
                linha[
                    "RECENTE"
                ]
            )
        else:
            referencia = _numero(
                linha[
                    "BASE"
                ]
            )
            recente = _numero(
                linha[
                    "RECENTE"
                ]
            )

        if (
            referencia is None
            or recente is None
        ):
            continue

        magnitude = abs(
            recente
            - referencia
        )

        candidatos.append(
            (
                magnitude,
                (
                    f"{codigo} — {linha['NOME']}: "
                    f"{_fmt_pct(referencia)} → "
                    f"{_fmt_pct(recente)} "
                    f"({linha['DELTA']}; "
                    f"{linha['TRAJETORIA']})."
                ),
            )
        )

    candidatos.sort(
        key=lambda item: item[
            0
        ],
        reverse=True,
    )

    return [
        texto
        for _, texto
        in candidatos[
            :limite
        ]
    ]


def _pontos_atencao(
    validacao: pd.DataFrame,
    analise: pd.DataFrame,
) -> list[
    str
]:
    pontos = []

    if not validacao.empty:
        problemas = (
            validacao.loc[
                validacao[
                    "STATUS"
                ].isin(
                    [
                        "ALERTA",
                        "BLOQUEIO",
                    ]
                )
            ]
        )

        for _, linha in problemas.iterrows():
            ano = linha.get(
                "ANO"
            )

            ano_txt = (
                ""
                if pd.isna(
                    ano
                )
                else (
                    f" ({int(ano)})"
                )
            )

            pontos.append(
                f"{linha['STATUS']}: "
                f"{linha['TESTE']}{ano_txt} — "
                f"{linha['DETALHE']}"
            )

    for _, linha in analise.iterrows():
        if str(
            linha[
                "STATUS_RECENTE"
            ]
        ) in {
            "N/D",
            "N/A",
        }:
            pontos.append(
                f"{linha['INDICADOR']}: "
                f"{linha['INTERPRETACAO']}"
            )

    if not pontos:
        pontos.append(
            "Nenhum alerta ou bloqueio identificado "
            "nas verificações utilizadas pelo relatório setorial."
        )

    return pontos


def _sinteses(
    analise: pd.DataFrame,
) -> dict[
    str,
    str
]:
    def registro(
        codigo: str,
    ):
        linhas = analise.loc[
            analise[
                "INDICADOR"
            ].eq(
                codigo
            )
        ]

        return (
            None
            if linhas.empty
            else linhas.iloc[
                0
            ]
        )

    cap = registro(
        "CAP_CONTABIL"
    )
    pf = registro(
        "PF_ATIVO"
    )

    cresc_at = registro(
        "CRESC_ATIVO"
    )
    cresc_pl = registro(
        "CRESC_PL"
    )
    cresc_ll = registro(
        "CRESC_LL"
    )

    rbi = registro(
        "RBI_ATIVO_MEDIO"
    )
    pre = registro(
        "PRETRIB_ATIVO_MEDIO"
    )
    roa = registro(
        "ROA"
    )
    roe = registro(
        "ROE"
    )

    return {
        "Capitalização e Funding": (
            f"A Capitalização Contábil encerrou o período em "
            f"{_fmt_pct(cap['RECENTE']) if cap is not None else 'N/D'}, "
            f"enquanto Passivos Financeiros/Ativo encerrou em "
            f"{_fmt_pct(pf['RECENTE']) if pf is not None else 'N/D'}. "
            f"Essas métricas descrevem a estrutura contábil de "
            f"capitalização e funding, sem substituir indicadores "
            f"prudenciais como Basileia."
        ),

        "Crescimento": (
            f"No exercício recente, o Ativo Total variou "
            f"{_fmt_pct(cresc_at['RECENTE']) if cresc_at is not None else 'N/D'}, "
            f"o Patrimônio Líquido "
            f"{_fmt_pct(cresc_pl['RECENTE']) if cresc_pl is not None else 'N/D'} "
            f"e o Lucro Líquido "
            f"{_fmt_pct(cresc_ll['RECENTE']) if cresc_ll is not None else 'N/D'}. "
            f"As taxas são apresentadas somente quando existe "
            f"base anterior comparável."
        ),

        "Intermediação e Rentabilidade": (
            f"O RBI/Ativo Médio encerrou em "
            f"{_fmt_pct(rbi['RECENTE']) if rbi is not None else 'N/D'}, "
            f"o Resultado Pré-Tributos/Ativo Médio em "
            f"{_fmt_pct(pre['RECENTE']) if pre is not None else 'N/D'}, "
            f"o ROA em "
            f"{_fmt_pct(roa['RECENTE']) if roa is not None else 'N/D'} "
            f"e o ROE em "
            f"{_fmt_pct(roe['RECENTE']) if roe is not None else 'N/D'}. "
            f"RBI/Ativo Médio não deve ser interpretado como NIM."
        ),
    }


def gerar_relatorio_financeiro(
    cd_cvm: str,
    nome_empresa: str,
    anos: list[int],
) -> dict[
    str,
    object
]:
    anos = sorted(
        {
            int(
                ano
            )
            for ano in anos
        }
    )

    if len(
        anos
    ) < 2:
        raise ValueError(
            "O relatório setorial requer pelo menos dois exercícios."
        )

    base_dados = _montar_base(
        cd_cvm,
        anos,
    )

    analise = pd.DataFrame(
        [
            _linha_analise(
                base_dados,
                codigo,
                anos,
            )
            for codigo in ORDEM
        ]
    )

    validacao = validar_empresa(
        cd_cvm,
        anos=anos,
    )

    status = status_geral(
        validacao
    )

    sinteses = _sinteses(
        analise
    )

    principais = _principais_mudancas(
        analise
    )

    pontos = _pontos_atencao(
        validacao,
        analise,
    )

    if status == "BLOQUEIO":
        resumo = (
            f"A análise setorial de {nome_empresa} cobre "
            f"{anos[0]}–{anos[-1]}, mas a camada interpretativa "
            f"está suspensa porque a validação identificou "
            f"bloqueio de integridade."
        )

        conclusao = (
            "Os valores permanecem disponíveis para diagnóstico, "
            "mas não devem sustentar conclusão financeira enquanto "
            "o bloqueio persistir."
        )

    else:
        recente = (
            analise.set_index(
                "INDICADOR"
            )
        )

        resumo = (
            f"A análise de {nome_empresa} cobre o período "
            f"{anos[0]}–{anos[-1]} e utiliza nove indicadores "
            f"aplicáveis ao layout financeiro: sete métricas setoriais "
            f"mais ROA e ROE do motor original. "
            f"No exercício recente, a Capitalização Contábil foi de "
            f"{_fmt_pct(recente.loc['CAP_CONTABIL', 'RECENTE'])}, "
            f"Passivos Financeiros/Ativo de "
            f"{_fmt_pct(recente.loc['PF_ATIVO', 'RECENTE'])}, "
            f"ROA de {_fmt_pct(recente.loc['ROA', 'RECENTE'])} "
            f"e ROE de {_fmt_pct(recente.loc['ROE', 'RECENTE'])}. "
            f"Indicadores tradicionais incompatíveis com instituições "
            f"financeiras permanecem classificados como N/A e não são "
            f"usados nesta síntese."
        )

        conclusao = (
            f"No período analisado, a leitura financeira deve combinar "
            f"capitalização contábil, estrutura de passivos, crescimento, "
            f"resultado da intermediação e rentabilidade. "
            f"ROA e ROE permanecem comparáveis dentro da metodologia "
            f"já validada; Capitalização Contábil não equivale a capital "
            f"regulatório, e RBI/Ativo Médio não equivale a NIM. "
            f"O relatório não atribui nota automática de saúde financeira."
        )

        if status == "ALERTA":
            conclusao += (
                " As ressalvas registradas na validação devem "
                "acompanhar a interpretação."
            )

    return {
        "STATUS_VALIDACAO": status,
        "ANOS": anos,
        "RESUMO_EXECUTIVO": resumo,
        "ANALISE_INDICADORES": analise,
        "SINTESES_GRUPOS": sinteses,
        "PRINCIPAIS_MUDANCAS": principais,
        "PONTOS_ATENCAO": pontos,
        "CONCLUSAO": conclusao,
        "VALIDACAO": validacao,
        "DUPONT": pd.DataFrame(),
        "INDICADORES_SETORIAIS": base_dados,
        "METODOLOGIA": (
            "Relatório determinístico para layout FINANCEIRA; "
            "sete indicadores setoriais + ROA/ROE; "
            "sem DuPont tradicional; sem indicadores prudenciais "
            "não disponíveis na DFP."
        ),
    }


__all__ = [
    "formatar_delta_pp",
    "gerar_relatorio_financeiro",
]

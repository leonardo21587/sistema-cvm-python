from __future__ import annotations

import pandas as pd

from src.indicadores import (
    quadro_indicadores,
    validar_dupont,
)

from src.validacao import (
    validar_empresa,
    status_geral,
)


# ============================================================
# METADADOS
# ============================================================

NOMES = {
    "IPL": "Imobilização do Patrimônio Líquido",
    "PCT": "Participação de Capital de Terceiros",
    "CE": "Composição do Endividamento",
    "EFSAT": "Endividamento Financeiro sobre Ativo Total",
    "LG": "Liquidez Geral",
    "LC": "Liquidez Corrente",
    "LS": "Liquidez Seca",
    "ICJ": "Índice de Cobertura de Juros",
    "GA": "Giro do Ativo",
    "RSV": "Retorno sobre Vendas",
    "ROA": "Retorno sobre o Ativo",
    "ROE": "Retorno sobre o Patrimônio Líquido",
}


GRUPOS = {
    "Estrutura de Capital": [
        "IPL",
        "PCT",
        "CE",
        "EFSAT",
    ],
    "Liquidez": [
        "LG",
        "LC",
        "LS",
        "ICJ",
    ],
    "Lucratividade/Desempenho": [
        "GA",
        "RSV",
        "ROA",
        "ROE",
    ],
}


PERCENTUAIS = {
    "IPL",
    "PCT",
    "CE",
    "EFSAT",
    "RSV",
    "ROA",
    "ROE",
}


CONTEXTUAIS = {
    "PCT",
    "CE",
    "EFSAT",
}


# ============================================================
# TOLERÂNCIAS NARRATIVAS
# ============================================================

# Estas tolerâncias servem somente para classificar
# estabilidade narrativa.
# Não representam limites econômicos ensinados pelo professor.

TOLERANCIAS = {
    "PERCENTUAL": {
        "ABS": 0.0025,   # 0,25 p.p.
        "REL": 0.02,
    },
    "RAZAO": {
        "ABS": 0.02,
        "REL": 0.02,
    },
    "ICJ": {
        "ABS": 0.10,
        "REL": 0.02,
    },
}


TRAJETORIAS = {
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


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def _numero(valor):

    if valor is None or pd.isna(valor):
        return None

    try:
        return float(valor)

    except (TypeError, ValueError):
        return None


def _formatar(
    codigo: str,
    valor,
) -> str:

    valor = _numero(valor)

    if valor is None:
        return "N/D"

    if codigo in PERCENTUAIS:

        numero = (
            f"{valor * 100:.2f}"
            .replace(".", ",")
        )

        return f"{numero}%"

    if codigo in {
        "ICJ",
        "GA",
    }:

        numero = (
            f"{valor:.2f}"
            .replace(".", ",")
        )

        return f"{numero} vezes"

    return (
        f"{valor:.2f}"
        .replace(".", ",")
    )


def _tolerancia(
    codigo: str,
    referencia: float,
) -> float:

    if codigo in PERCENTUAIS:

        regra = TOLERANCIAS[
            "PERCENTUAL"
        ]

    elif codigo == "ICJ":

        regra = TOLERANCIAS[
            "ICJ"
        ]

    else:

        regra = TOLERANCIAS[
            "RAZAO"
        ]

    return max(
        regra["ABS"],
        regra["REL"]
        * abs(float(referencia)),
    )


def _movimento(
    codigo: str,
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

    tolerancia = (
        _tolerancia(
            codigo,
            anterior,
        )
    )

    if abs(delta) <= tolerancia:
        return "→"

    if delta > 0:
        return "↑"

    return "↓"


def _posicao_final(
    codigo: str,
    base,
    recente,
) -> str:

    base = _numero(
        base
    )

    recente = _numero(
        recente
    )

    if (
        base is None
        or recente is None
    ):
        return "N/D"

    tolerancia = (
        _tolerancia(
            codigo,
            base,
        )
    )

    diferenca = (
        recente
        - base
    )

    if abs(
        diferenca
    ) <= tolerancia:
        return "próximo da base"

    if diferenca > 0:
        return "acima da base"

    return "abaixo da base"


def _delta_texto(
    codigo: str,
    base,
    recente,
) -> str:

    base = _numero(base)
    recente = _numero(recente)

    if (
        base is None
        or recente is None
    ):
        return "N/D"

    delta = recente - base

    if codigo in PERCENTUAIS:

        pontos = (
            delta * 100
        )

        sinal = (
            "+"
            if pontos > 0
            else ""
        )

        numero = (
            f"{pontos:.2f}"
            .replace(".", ",")
        )

        return (
            f"{sinal}{numero} p.p."
        )

    sinal = (
        "+"
        if delta > 0
        else ""
    )

    numero = (
        f"{delta:.2f}"
        .replace(".", ",")
    )

    if codigo in {
        "GA",
        "ICJ",
    }:
        return (
            f"{sinal}{numero} vezes"
        )

    return (
        f"{sinal}{numero}"
    )


def _trajetoria(
    codigo: str,
    base,
    intermediario,
    recente,
) -> tuple[str, str, str]:

    if intermediario is None:

        movimento = (
            _movimento(
                codigo,
                base,
                recente,
            )
        )

        traducao = {
            "↑": "aumento no período",
            "↓": "redução no período",
            "→": "praticamente estável",
            "N/D": "N/D",
        }

        return (
            traducao[
                movimento
            ],
            movimento,
            "N/D",
        )


    mov_1 = _movimento(
        codigo,
        base,
        intermediario,
    )

    mov_2 = _movimento(
        codigo,
        intermediario,
        recente,
    )


    if (
        mov_1 == "N/D"
        or mov_2 == "N/D"
    ):

        return (
            "N/D",
            mov_1,
            mov_2,
        )


    classificacao = (
        TRAJETORIAS.get(
            (
                mov_1,
                mov_2,
            ),
            "comportamento misto",
        )
    )


    return (
        classificacao,
        mov_1,
        mov_2,
    )


def _linha_indicador(
    quadro: pd.DataFrame,
    codigo: str,
):

    linhas = quadro.loc[
        quadro[
            "INDICADOR"
        ]
        .astype(str)
        .eq(codigo)
    ]

    if linhas.empty:
        return None

    if len(linhas) != 1:

        raise RuntimeError(
            "Indicador duplicado no quadro: "
            f"{codigo}"
        )

    return linhas.iloc[0]


# ============================================================
# INTERPRETAÇÃO INDIVIDUAL
# ============================================================

def _interpretacao_individual(
    codigo: str,
    base,
    intermediario,
    recente,
    trajetoria: str,
) -> str:

    base_num = _numero(
        base
    )

    recente_num = _numero(
        recente
    )

    if (
        base_num is None
        or recente_num is None
    ):

        return (
            "Não há informação suficiente para "
            "produzir interpretação deste indicador."
        )


    recente_fmt = _formatar(
        codigo,
        recente_num,
    )


    # ========================================================
    # ESTRUTURA DE CAPITAL
    # ========================================================

    if codigo == "IPL":

        return (
            f"O IPL apresentou {trajetoria}. "
            f"No exercício recente, "
            f"{recente_fmt} do patrimônio líquido "
            f"correspondia a investimentos, imobilizado "
            f"e intangível. "
            f"O movimento descreve alteração no grau "
            f"de imobilização dos recursos próprios."
        )


    if codigo == "PCT":

        return (
            f"A Participação de Capital de Terceiros "
            f"apresentou {trajetoria}. "
            f"No exercício recente, o capital de terceiros "
            f"equivalia a {recente_fmt} do patrimônio líquido. "
            f"O indicador descreve a relação entre recursos "
            f"de terceiros e capital próprio e deve ser "
            f"interpretado conjuntamente com liquidez, "
            f"estrutura de vencimentos e geração de resultado."
        )


    if codigo == "CE":

        return (
            f"A Composição do Endividamento apresentou "
            f"{trajetoria}. "
            f"No exercício recente, {recente_fmt} do capital "
            f"de terceiros estava concentrado no curto prazo. "
            f"A leitura deve considerar simultaneamente "
            f"a estrutura de vencimentos e a posição "
            f"de liquidez da companhia."
        )


    if codigo == "EFSAT":

        return (
            f"O Endividamento Financeiro sobre o Ativo Total "
            f"apresentou {trajetoria}. "
            f"No exercício recente, empréstimos e "
            f"financiamentos representavam {recente_fmt} "
            f"do ativo total. "
            f"O indicador descreve a participação da dívida "
            f"financeira na estrutura patrimonial."
        )


    # ========================================================
    # LIQUIDEZ
    # ========================================================

    if codigo == "LG":

        if recente_num >= 1:

            referencia = (
                "os ativos realizáveis superavam "
                "contabilmente as obrigações totais"
            )

        else:

            referencia = (
                "os ativos realizáveis eram inferiores "
                "às obrigações totais"
            )


        return (
            f"A Liquidez Geral apresentou {trajetoria}. "
            f"No exercício recente, a razão foi de "
            f"{recente_fmt}, indicando que {referencia}."
        )


    if codigo == "LC":

        if recente_num >= 1:

            referencia = (
                "o ativo circulante superava "
                "o passivo circulante"
            )

        else:

            referencia = (
                "o ativo circulante não alcançava "
                "o passivo circulante"
            )


        return (
            f"A Liquidez Corrente apresentou {trajetoria}. "
            f"No exercício recente, a razão foi de "
            f"{recente_fmt}, de modo que {referencia}."
        )


    if codigo == "LS":

        if recente_num >= 1:

            referencia = (
                "os componentes considerados na liquidez "
                "seca cobriam contabilmente o passivo "
                "circulante"
            )

        else:

            referencia = (
                "os componentes considerados na liquidez "
                "seca não cobriam integralmente o passivo "
                "circulante"
            )


        return (
            f"A Liquidez Seca apresentou {trajetoria}. "
            f"No exercício recente, o indicador foi de "
            f"{recente_fmt}; assim, {referencia}."
        )


    if codigo == "ICJ":

        if recente_num < 0:

            return (
                f"O Índice de Cobertura de Juros apresentou "
                f"{trajetoria} e encerrou o período em "
                f"{recente_fmt}. "
                f"O valor negativo decorre de EBIT negativo "
                f"e não deve ser interpretado como cobertura "
                f"positiva das despesas financeiras."
            )


        return (
            f"O Índice de Cobertura de Juros apresentou "
            f"{trajetoria}. "
            f"No exercício recente, o EBIT correspondia a "
            f"{recente_fmt} o valor absoluto das despesas "
            f"financeiras."
        )


    # ========================================================
    # LUCRATIVIDADE / DESEMPENHO
    # ========================================================

    if codigo == "GA":

        ga_fmt = (
            f"{recente_num:.2f}"
            .replace(".", ",")
        )

        return (
            f"O Giro do Ativo apresentou {trajetoria}. "
            f"No exercício recente, cada R$ 1,00 de ativo "
            f"médio gerou aproximadamente R$ {ga_fmt} "
            f"de receita líquida. "
            f"O indicador mede a intensidade com que "
            f"os ativos são utilizados na geração de receita."
        )


    if codigo == "RSV":

        return (
            f"O Retorno sobre Vendas apresentou "
            f"{trajetoria}. "
            f"No exercício recente, o resultado líquido "
            f"representou {recente_fmt} da receita líquida, "
            f"indicando a parcela da receita convertida "
            f"em resultado final."
        )


    if codigo == "ROA":

        return (
            f"O ROA apresentou {trajetoria}. "
            f"No exercício recente, o resultado líquido "
            f"correspondeu a {recente_fmt} do ativo médio. "
            f"A decomposição DuPont permite relacionar "
            f"esse resultado ao Giro do Ativo e ao "
            f"Retorno sobre Vendas."
        )


    if codigo == "ROE":

        return (
            f"O ROE apresentou {trajetoria}. "
            f"No exercício recente, o resultado líquido "
            f"correspondeu a {recente_fmt} do patrimônio "
            f"líquido médio ajustado. "
            f"O denominador segue a metodologia específica "
            f"do professor, não sendo utilizada a média "
            f"simples do patrimônio líquido."
        )


    return (
        f"O indicador apresentou {trajetoria} "
        f"e encerrou o período em {recente_fmt}."
    )


# ============================================================
# ANÁLISE DOS 12 INDICADORES
# ============================================================

def analisar_indicadores(
    quadro: pd.DataFrame,
    anos: list[int],
) -> pd.DataFrame:

    anos = sorted(
        int(ano)
        for ano in anos
    )


    if len(anos) < 2:
        return pd.DataFrame(
            columns=[
                "GRUPO",
                "INDICADOR",
                "NOME",
                "BASE",
                "INTERMEDIARIO",
                "RECENTE",
                "MOV_1",
                "MOV_2",
                "DELTA",
                "TRAJETORIA",
                "POSICAO_FINAL",
                "INTERPRETACAO",
            ]
        )


    ano_base = anos[0]

    ano_recente = anos[-1]


    ano_intermediario = (
        anos[1]
        if len(anos) >= 3
        else None
    )


    registros = []


    for grupo, codigos in GRUPOS.items():

        for codigo in codigos:

            linha = _linha_indicador(
                quadro,
                codigo,
            )


            if linha is None:

                registros.append(
                    {
                        "GRUPO": grupo,
                        "INDICADOR": codigo,
                        "NOME": NOMES[codigo],
                        "BASE": None,
                        "INTERMEDIARIO": None,
                        "RECENTE": None,
                        "MOV_1": "N/D",
                        "MOV_2": "N/D",
                        "DELTA": "N/D",
                        "TRAJETORIA": "N/D",
                        "POSICAO_FINAL": "N/D",
                        "INTERPRETACAO": (
                            "Indicador não disponível."
                        ),
                    }
                )

                continue


            base = (
                linha[ano_base]
                if ano_base in linha.index
                else None
            )


            intermediario = (
                linha[ano_intermediario]
                if (
                    ano_intermediario is not None
                    and ano_intermediario
                    in linha.index
                )
                else None
            )


            recente = (
                linha[ano_recente]
                if ano_recente
                in linha.index
                else None
            )


            (
                trajetoria,
                mov_1,
                mov_2,
            ) = _trajetoria(
                codigo,
                base,
                intermediario,
                recente,
            )


            posicao = (
                _posicao_final(
                    codigo,
                    base,
                    recente,
                )
            )


            delta = (
                _delta_texto(
                    codigo,
                    base,
                    recente,
                )
            )


            interpretacao = (
                _interpretacao_individual(
                    codigo,
                    base,
                    intermediario,
                    recente,
                    trajetoria,
                )
            )


            registros.append(
                {
                    "GRUPO": grupo,
                    "INDICADOR": codigo,
                    "NOME": NOMES[codigo],
                    "BASE": _numero(
                        base
                    ),
                    "INTERMEDIARIO": _numero(
                        intermediario
                    ),
                    "RECENTE": _numero(
                        recente
                    ),
                    "MOV_1": mov_1,
                    "MOV_2": mov_2,
                    "DELTA": delta,
                    "TRAJETORIA": trajetoria,
                    "POSICAO_FINAL": posicao,
                    "INTERPRETACAO": interpretacao,
                }
            )


    return pd.DataFrame(
        registros
    )


# ============================================================
# BUSCA DE REGISTROS
# ============================================================

def _registro(
    analise: pd.DataFrame,
    codigo: str,
):

    if (
        analise is None
        or analise.empty
        or "INDICADOR" not in analise.columns
    ):
        return None

    linha = analise.loc[
        analise[
            "INDICADOR"
        ] == codigo
    ]

    if linha.empty:
        return None

    return linha.iloc[0]


# ============================================================
# SÍNTESE — ESTRUTURA DE CAPITAL
# ============================================================

def _resumo_estrutura(
    analise: pd.DataFrame,
) -> str:

    ipl = _registro(
        analise,
        "IPL",
    )

    pct = _registro(
        analise,
        "PCT",
    )

    ce = _registro(
        analise,
        "CE",
    )

    efsat = _registro(
        analise,
        "EFSAT",
    )


    if any(
        item is None
        for item in [
            ipl,
            pct,
            ce,
            efsat,
        ]
    ):

        return (
            "A estrutura de capital não pôde ser "
            "sintetizada integralmente."
        )


    return (
        f"O IPL apresentou {ipl['TRAJETORIA']} e encerrou "
        f"o período {ipl['POSICAO_FINAL']}. "
        f"A PCT apresentou {pct['TRAJETORIA']}, enquanto "
        f"a Composição do Endividamento apresentou "
        f"{ce['TRAJETORIA']} e o EFSAT apresentou "
        f"{efsat['TRAJETORIA']}. "
        f"PCT, CE e EFSAT são tratados como indicadores "
        f"contextuais: seus movimentos descrevem alterações "
        f"na composição das fontes de financiamento e do "
        f"endividamento, sem julgamento automático isolado."
    )


# ============================================================
# SÍNTESE — LIQUIDEZ
# ============================================================

def _resumo_liquidez(
    analise: pd.DataFrame,
) -> str:

    lg = _registro(
        analise,
        "LG",
    )

    lc = _registro(
        analise,
        "LC",
    )

    ls = _registro(
        analise,
        "LS",
    )

    icj = _registro(
        analise,
        "ICJ",
    )


    if any(
        item is None
        for item in [
            lg,
            lc,
            ls,
            icj,
        ]
    ):

        return (
            "A liquidez não pôde ser sintetizada "
            "integralmente."
        )


    recente_lc = _numero(
        lc["RECENTE"]
    )

    recente_ls = _numero(
        ls["RECENTE"]
    )


    cobertura = []


    if recente_lc is not None:

        if recente_lc >= 1:

            cobertura.append(
                "a Liquidez Corrente ficou acima da unidade"
            )

        else:

            cobertura.append(
                "a Liquidez Corrente ficou abaixo da unidade"
            )


    if recente_ls is not None:

        if recente_ls >= 1:

            cobertura.append(
                "a Liquidez Seca também superou a unidade"
            )

        else:

            cobertura.append(
                "a Liquidez Seca ficou abaixo da unidade"
            )


    cobertura_texto = (
        "; ".join(
            cobertura
        )
        if cobertura
        else (
            "as relações recentes exigem "
            "leitura individual"
        )
    )


    return (
        f"A Liquidez Geral apresentou "
        f"{lg['TRAJETORIA']}, a Liquidez Corrente "
        f"{lc['TRAJETORIA']} e a Liquidez Seca "
        f"{ls['TRAJETORIA']}. "
        f"No exercício recente, {cobertura_texto}. "
        f"O Índice de Cobertura de Juros apresentou "
        f"{icj['TRAJETORIA']} e terminou em "
        f"{_formatar('ICJ', icj['RECENTE'])}. "
        f"A leitura conjunta permite separar cobertura "
        f"patrimonial, cobertura das obrigações de curto "
        f"prazo e capacidade operacional de absorver "
        f"despesas financeiras."
    )


# ============================================================
# DUPONT
# ============================================================

def _canal_dupont(
    ga,
    rsv,
) -> str:

    ga_base = _numero(
        ga["BASE"]
    )

    ga_rec = _numero(
        ga["RECENTE"]
    )

    rsv_base = _numero(
        rsv["BASE"]
    )

    rsv_rec = _numero(
        rsv["RECENTE"]
    )


    if any(
        valor is None
        for valor in [
            ga_base,
            ga_rec,
            rsv_base,
            rsv_rec,
        ]
    ):

        return (
            "A decomposição dos canais do ROA "
            "não pôde ser comparada integralmente."
        )


    mov_ga = _movimento(
        "GA",
        ga_base,
        ga_rec,
    )

    mov_rsv = _movimento(
        "RSV",
        rsv_base,
        rsv_rec,
    )


    if (
        mov_ga == "→"
        and mov_rsv == "↓"
    ):

        return (
            "A variação do ROA esteve associada "
            "principalmente ao canal de margem, "
            "pois o Giro do Ativo permaneceu "
            "relativamente estável enquanto o "
            "Retorno sobre Vendas recuou."
        )


    if (
        mov_ga == "→"
        and mov_rsv == "↑"
    ):

        return (
            "A variação do ROA esteve associada "
            "principalmente ao canal de margem, "
            "pois o Giro do Ativo permaneceu "
            "relativamente estável enquanto o "
            "Retorno sobre Vendas aumentou."
        )


    if (
        mov_ga == "↓"
        and mov_rsv == "→"
    ):

        return (
            "A variação do ROA esteve associada "
            "principalmente à redução do Giro do Ativo, "
            "com margem relativamente estável."
        )


    if (
        mov_ga == "↑"
        and mov_rsv == "→"
    ):

        return (
            "A variação do ROA esteve associada "
            "principalmente ao aumento do Giro do Ativo, "
            "com margem relativamente estável."
        )


    if (
        mov_ga == mov_rsv
        and mov_ga in {
            "↑",
            "↓",
        }
    ):

        direcao = (
            "expansão"
            if mov_ga == "↑"
            else "redução"
        )

        return (
            f"Na decomposição DuPont, giro e margem "
            f"se moveram na mesma direção, contribuindo "
            f"conjuntamente para a {direcao} do ROA."
        )


    if {
        mov_ga,
        mov_rsv,
    } == {
        "↑",
        "↓",
    }:

        return (
            "Na decomposição DuPont, Giro do Ativo e "
            "Retorno sobre Vendas se moveram em direções "
            "opostas, produzindo efeitos parcialmente "
            "compensatórios sobre o ROA."
        )


    return (
        "A decomposição DuPont indica combinação "
        "de movimentos entre giro e margem."
    )


# ============================================================
# SÍNTESE — DESEMPENHO
# ============================================================

def _resumo_desempenho(
    analise: pd.DataFrame,
    dupont: pd.DataFrame,
) -> str:

    ga = _registro(
        analise,
        "GA",
    )

    rsv = _registro(
        analise,
        "RSV",
    )

    roa = _registro(
        analise,
        "ROA",
    )

    roe = _registro(
        analise,
        "ROE",
    )


    if any(
        item is None
        for item in [
            ga,
            rsv,
            roa,
            roe,
        ]
    ):

        return (
            "O desempenho não pôde ser sintetizado "
            "integralmente."
        )


    if dupont.empty:

        status_dupont = "N/D"

    elif (
        dupont[
            "STATUS"
        ]
        .eq("OK")
        .all()
    ):

        status_dupont = "OK"

    else:

        status_dupont = "RESSALVA"


    return (
        f"O Giro do Ativo apresentou "
        f"{ga['TRAJETORIA']}; o Retorno sobre Vendas, "
        f"{rsv['TRAJETORIA']}; o ROA, "
        f"{roa['TRAJETORIA']}; e o ROE, "
        f"{roe['TRAJETORIA']}. "
        f"{_canal_dupont(ga, rsv)} "
        f"A identidade DuPont ROA = GA × RSV "
        f"apresentou status {status_dupont} "
        f"nos exercícios analisados."
    )


# ============================================================
# PRINCIPAIS MUDANÇAS
# ============================================================

def _score_mudanca(
    codigo: str,
    base,
    recente,
):

    base = _numero(
        base
    )

    recente = _numero(
        recente
    )


    if (
        base is None
        or recente is None
    ):
        return None


    delta = abs(
        recente
        - base
    )


    if codigo in PERCENTUAIS:

        denominador = 0.0025

    elif codigo == "ICJ":

        denominador = 0.10

    else:

        denominador = 0.02


    return (
        delta
        / denominador
    )


def principais_mudancas(
    analise: pd.DataFrame,
    limite: int = 3,
) -> list[str]:

    candidatos = []


    for _, linha in (
        analise.iterrows()
    ):

        codigo = str(
            linha["INDICADOR"]
        )


        score = _score_mudanca(
            codigo,
            linha["BASE"],
            linha["RECENTE"],
        )


        if score is None:
            continue


        texto = (
            f"{codigo} — {NOMES[codigo]}: "
            f"{_formatar(codigo, linha['BASE'])} → "
            f"{_formatar(codigo, linha['RECENTE'])} "
            f"({linha['DELTA']}; "
            f"{linha['TRAJETORIA']})."
        )


        candidatos.append(
            (
                score,
                texto,
            )
        )


    candidatos.sort(
        key=lambda item: item[0],
        reverse=True,
    )


    return [
        texto
        for _, texto
        in candidatos[:limite]
    ]


# ============================================================
# PONTOS DE ATENÇÃO
# ============================================================

def pontos_de_atencao(
    validacao: pd.DataFrame,
    analise: pd.DataFrame,
) -> list[str]:

    pontos = []


    if not validacao.empty:

        problemas = validacao.loc[
            validacao[
                "STATUS"
            ].isin(
                [
                    "ALERTA",
                    "BLOQUEIO",
                ]
            )
        ]


        for _, linha in (
            problemas.iterrows()
        ):

            ano = linha.get(
                "ANO"
            )


            if pd.isna(ano):

                ano_txt = ""

            else:

                ano_txt = (
                    f" ({int(ano)})"
                )


            pontos.append(
                f"{linha['STATUS']}: "
                f"{linha['TESTE']}{ano_txt} — "
                f"{linha['DETALHE']}"
            )


    for _, linha in (
        analise.iterrows()
    ):

        if (
            _numero(
                linha["RECENTE"]
            )
            is None
        ):

            pontos.append(
                f"{linha['INDICADOR']}: "
                f"resultado recente N/D; "
                f"não produzir interpretação conclusiva."
            )


    if not pontos:

        pontos.append(
            "Nenhum alerta ou bloqueio identificado "
            "nas verificações utilizadas pelo relatório."
        )


    return pontos


# ============================================================
# RESUMO EXECUTIVO
# ============================================================

def gerar_resumo_executivo(
    nome_empresa: str,
    anos: list[int],
    analise: pd.DataFrame,
    status_validacao: str,
) -> str:

    anos = sorted(
        anos
    )


    pct = _registro(
        analise,
        "PCT",
    )

    ce = _registro(
        analise,
        "CE",
    )

    efsat = _registro(
        analise,
        "EFSAT",
    )


    lg = _registro(
        analise,
        "LG",
    )

    lc = _registro(
        analise,
        "LC",
    )

    ls = _registro(
        analise,
        "LS",
    )


    ga = _registro(
        analise,
        "GA",
    )

    rsv = _registro(
        analise,
        "RSV",
    )

    roa = _registro(
        analise,
        "ROA",
    )

    roe = _registro(
        analise,
        "ROE",
    )


    frases = [
        (
            f"A análise de {nome_empresa} cobre o período "
            f"de {anos[0]} a {anos[-1]} e considera os "
            f"12 indicadores financeiros definidos "
            f"na metodologia adotada."
        )
    ]


    if all(
        item is not None
        for item in [
            pct,
            ce,
            efsat,
        ]
    ):

        frases.append(
            f"Na estrutura de capital, a PCT apresentou "
            f"{pct['TRAJETORIA']}, a Composição do "
            f"Endividamento apresentou "
            f"{ce['TRAJETORIA']} e o EFSAT apresentou "
            f"{efsat['TRAJETORIA']}. "
            f"Esses indicadores descrevem mudanças na "
            f"composição das fontes de financiamento e são "
            f"interpretados de maneira contextual."
        )


    if all(
        item is not None
        for item in [
            lg,
            lc,
            ls,
        ]
    ):

        frases.append(
            f"Na liquidez, LG apresentou "
            f"{lg['TRAJETORIA']}, LC "
            f"{lc['TRAJETORIA']} e LS "
            f"{ls['TRAJETORIA']}, encerrando o período "
            f"em {_formatar('LG', lg['RECENTE'])}, "
            f"{_formatar('LC', lc['RECENTE'])} e "
            f"{_formatar('LS', ls['RECENTE'])}, "
            f"respectivamente."
        )


    if all(
        item is not None
        for item in [
            ga,
            rsv,
            roa,
            roe,
        ]
    ):

        frases.append(
            f"Em desempenho, o Giro do Ativo apresentou "
            f"{ga['TRAJETORIA']}, o Retorno sobre Vendas "
            f"{rsv['TRAJETORIA']}, o ROA "
            f"{roa['TRAJETORIA']} e o ROE "
            f"{roe['TRAJETORIA']}."
        )


    if status_validacao == "OK":

        frases.append(
            "As verificações utilizadas pelo relatório "
            "não identificaram ressalvas ou bloqueios."
        )


    elif status_validacao == "INFO":

        frases.append(
            "A validação não identificou alertas ou "
            "bloqueios, embora existam registros "
            "informativos de auditoria."
        )


    elif status_validacao == "ALERTA":

        frases.append(
            "A análise permanece disponível, mas existem "
            "ressalvas de validação que devem acompanhar "
            "a interpretação."
        )


    else:

        frases.append(
            "Existe bloqueio de validação; interpretações "
            "financeiras conclusivas devem permanecer "
            "suspensas até a correção da integridade."
        )


    return " ".join(
        frases
    )


# ============================================================
# CONCLUSÃO
# ============================================================

def gerar_conclusao(
    analise: pd.DataFrame,
    status_validacao: str,
) -> str:

    if status_validacao == "BLOQUEIO":

        return (
            "A conclusão financeira está suspensa porque "
            "a validação identificou pelo menos um bloqueio "
            "de integridade. Os valores permanecem úteis "
            "para diagnóstico, mas não para uma síntese "
            "financeira conclusiva."
        )


    pct = _registro(
        analise,
        "PCT",
    )

    lc = _registro(
        analise,
        "LC",
    )

    ga = _registro(
        analise,
        "GA",
    )

    rsv = _registro(
        analise,
        "RSV",
    )

    roa = _registro(
        analise,
        "ROA",
    )


    frases = []


    if pct is not None:

        frases.append(
            f"A PCT apresentou {pct['TRAJETORIA']} e "
            f"encerrou o período em "
            f"{_formatar('PCT', pct['RECENTE'])}, "
            f"ante {_formatar('PCT', pct['BASE'])} "
            f"no exercício-base."
        )


    if lc is not None:

        frases.append(
            f"A Liquidez Corrente apresentou "
            f"{lc['TRAJETORIA']} e terminou em "
            f"{_formatar('LC', lc['RECENTE'])}, "
            f"comparada a {_formatar('LC', lc['BASE'])} "
            f"no exercício-base."
        )


    if all(
        item is not None
        for item in [
            ga,
            rsv,
            roa,
        ]
    ):

        frases.append(
            _canal_dupont(
                ga,
                rsv,
            )
        )

        frases.append(
            f"O ROA encerrou o período em "
            f"{_formatar('ROA', roa['RECENTE'])}, "
            f"ante {_formatar('ROA', roa['BASE'])} "
            f"no exercício-base, refletindo a combinação "
            f"observada entre giro e margem."
        )


    frases.append(
        "No conjunto, a leitura deve combinar estrutura "
        "de capital, liquidez e desempenho, evitando "
        "conclusões baseadas em um único indicador."
    )


    if status_validacao == "ALERTA":

        frases.append(
            "As ressalvas registradas na validação "
            "devem acompanhar essa conclusão."
        )


    return " ".join(
        frases
    )


# ============================================================
# RELATÓRIO COMPLETO
# ============================================================

def gerar_relatorio(
    cd_cvm: str,
    nome_empresa: str,
    anos: list[int],
) -> dict[str, object]:

    anos = sorted(
        int(ano)
        for ano in anos
    )


    # ========================================================
    # INDICADORES
    # ========================================================

    quadro = quadro_indicadores(
        cd_cvm,
        anos=anos,
    )


    if quadro.empty:

        return {
            "STATUS_VALIDACAO": "BLOQUEIO",

            "ANOS": anos,

            "RESUMO_EXECUTIVO": (
                "Não foi possível gerar o relatório "
                "porque os indicadores não estão disponíveis."
            ),

            "ANALISE_INDICADORES": (
                pd.DataFrame()
            ),

            "SINTESES_GRUPOS": {},

            "PRINCIPAIS_MUDANCAS": [],

            "PONTOS_ATENCAO": [
                "Indicadores indisponíveis."
            ],

            "CONCLUSAO": (
                "Relatório não disponível."
            ),

            "VALIDACAO": (
                pd.DataFrame()
            ),

            "DUPONT": (
                pd.DataFrame()
            ),
        }


    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    validacao = validar_empresa(
        cd_cvm,
        anos=anos,
    )


    status = status_geral(
        validacao
    )


    # ========================================================
    # ANÁLISE NARRATIVA
    # ========================================================

    analise = analisar_indicadores(
        quadro,
        anos,
    )


    dupont = validar_dupont(
        cd_cvm,
        anos=anos,
    )


    # ========================================================
    # BLOQUEIO
    # ========================================================

    if status == "BLOQUEIO":

        return {
            "STATUS_VALIDACAO": status,

            "ANOS": anos,

            "RESUMO_EXECUTIVO": (
                f"A análise de {nome_empresa} foi "
                f"interrompida na camada interpretativa "
                f"porque a validação encontrou bloqueio "
                f"de integridade. "
                f"Os valores permanecem disponíveis "
                f"apenas para diagnóstico."
            ),

            "ANALISE_INDICADORES": (
                analise
            ),

            "SINTESES_GRUPOS": {},

            "PRINCIPAIS_MUDANCAS": [],

            "PONTOS_ATENCAO": (
                pontos_de_atencao(
                    validacao,
                    analise,
                )
            ),

            "CONCLUSAO": (
                gerar_conclusao(
                    analise,
                    status,
                )
            ),

            "VALIDACAO": validacao,

            "DUPONT": dupont,
        }


    # ========================================================
    # SÍNTESES
    # ========================================================

    sinteses = {

        "Estrutura de Capital": (
            _resumo_estrutura(
                analise
            )
        ),

        "Liquidez": (
            _resumo_liquidez(
                analise
            )
        ),

        "Lucratividade/Desempenho": (
            _resumo_desempenho(
                analise,
                dupont,
            )
        ),
    }


    return {

        "STATUS_VALIDACAO": (
            status
        ),

        "ANOS": (
            anos
        ),

        "RESUMO_EXECUTIVO": (
            gerar_resumo_executivo(
                nome_empresa,
                anos,
                analise,
                status,
            )
        ),

        "ANALISE_INDICADORES": (
            analise
        ),

        "SINTESES_GRUPOS": (
            sinteses
        ),

        "PRINCIPAIS_MUDANCAS": (
            principais_mudancas(
                analise
            )
        ),

        "PONTOS_ATENCAO": (
            pontos_de_atencao(
                validacao,
                analise,
            )
        ),

        "CONCLUSAO": (
            gerar_conclusao(
                analise,
                status,
            )
        ),

        "VALIDACAO": (
            validacao
        ),

        "DUPONT": (
            dupont
        ),
    }


# ============================================================
# TESTE NO TERMINAL
# ============================================================

def main():

    cd_cvm = (
        "004170"
    )

    nome_empresa = (
        "VALE S.A."
    )

    anos = [
        2023,
        2024,
        2025,
    ]


    relatorio = gerar_relatorio(
        cd_cvm,
        nome_empresa,
        anos,
    )


    print(
        "=" * 90
    )

    print(
        "RELATÓRIO AUTOMÁTICO — SISTEMA CVM"
    )

    print(
        "=" * 90
    )


    # ========================================================
    # STATUS
    # ========================================================

    print()

    print(
        "STATUS DE VALIDAÇÃO:"
    )

    print(
        relatorio[
            "STATUS_VALIDACAO"
        ]
    )


    # ========================================================
    # RESUMO
    # ========================================================

    print()

    print(
        "RESUMO EXECUTIVO"
    )

    print(
        "-" * 90
    )

    print(
        relatorio[
            "RESUMO_EXECUTIVO"
        ]
    )


    # ========================================================
    # SÍNTESES
    # ========================================================

    print()

    print(
        "SÍNTESES POR GRUPO"
    )

    print(
        "-" * 90
    )


    for grupo, texto in (
        relatorio[
            "SINTESES_GRUPOS"
        ].items()
    ):

        print()

        print(
            grupo.upper()
        )

        print(
            texto
        )


    # ========================================================
    # MUDANÇAS
    # ========================================================

    print()

    print(
        "PRINCIPAIS MUDANÇAS"
    )

    print(
        "-" * 90
    )


    for item in (
        relatorio[
            "PRINCIPAIS_MUDANCAS"
        ]
    ):

        print(
            f"- {item}"
        )


    # ========================================================
    # PONTOS DE ATENÇÃO
    # ========================================================

    print()

    print(
        "PONTOS DE ATENÇÃO"
    )

    print(
        "-" * 90
    )


    for item in (
        relatorio[
            "PONTOS_ATENCAO"
        ]
    ):

        print(
            f"- {item}"
        )


    # ========================================================
    # ANÁLISE INDIVIDUAL
    # ========================================================

    print()

    print(
        "ANÁLISE INDIVIDUAL"
    )

    print(
        "-" * 90
    )


    analise = (
        relatorio[
            "ANALISE_INDICADORES"
        ]
    )


    if not analise.empty:

        for _, linha in (
            analise.iterrows()
        ):

            codigo = (
                linha[
                    "INDICADOR"
                ]
            )


            print()

            print(
                f"{codigo} — "
                f"{linha['NOME']}"
            )

            print(
                f"Trajetória: "
                f"{linha['TRAJETORIA']}"
            )

            print(
                f"Variação base → recente: "
                f"{linha['DELTA']}"
            )

            print(
                linha[
                    "INTERPRETACAO"
                ]
            )


    # ========================================================
    # CONCLUSÃO
    # ========================================================

    print()

    print(
        "CONCLUSÃO"
    )

    print(
        "-" * 90
    )

    print(
        relatorio[
            "CONCLUSAO"
        ]
    )


if __name__ == "__main__":
    main()
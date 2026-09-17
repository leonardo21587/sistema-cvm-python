from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import PROCESSED_DIR
from src.banco import anos_disponiveis, carregar_demonstracao


ARQUIVO_AUXILIAR = PROCESSED_DIR / "saldos_auxiliares_2022.parquet"


FORMULAS = {
    "IPL": "(Investimentos + Imobilizado + Intangível) / PL",
    "PCT": "(PC + PNC) / PL",
    "CE": "PC / (PC + PNC)",
    "EFSAT": "(Empréstimos CP + Empréstimos LP) / Ativo Total",
    "LG": "(AC + RLP) / (PC + PNC)",
    "LC": "AC / PC",
    "LS": "(Disponível + Aplicações Financeiras + Contas a Receber) / PC",
    "ICJ": "EBIT / ABS(Despesas Financeiras)",
    "GA": "Receita Líquida / Ativo Total Médio",
    "RSV": "Lucro Líquido / Receita Líquida",
    "ROA": "Lucro Líquido / Ativo Total Médio",
    "ROE": "Lucro Líquido / PL Médio Ajustado",
}

GRUPOS = {
    "IPL": "Estrutura de Capital",
    "PCT": "Estrutura de Capital",
    "CE": "Estrutura de Capital",
    "EFSAT": "Estrutura de Capital",
    "LG": "Liquidez",
    "LC": "Liquidez",
    "LS": "Liquidez",
    "ICJ": "Liquidez",
    "GA": "Lucratividade/Desempenho",
    "RSV": "Lucratividade/Desempenho",
    "ROA": "Lucratividade/Desempenho",
    "ROE": "Lucratividade/Desempenho",
}

UNIDADES = {
    "IPL": "%",
    "PCT": "%",
    "CE": "%",
    "EFSAT": "%",
    "LG": "razão",
    "LC": "razão",
    "LS": "razão",
    "ICJ": "vezes",
    "GA": "vezes",
    "RSV": "%",
    "ROA": "%",
    "ROE": "%",
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


def _normalizar_cd_cvm(cd_cvm: str) -> str:
    return str(cd_cvm).strip().zfill(6)


def _valor_conta(
    df: pd.DataFrame,
    codigo: str,
) -> float | None:
    """
    Retorna o valor de uma conta quando ela existe de forma única.

    Conta ausente -> None.
    Conta existente com valor 0 -> 0.0.
    Mais de uma ocorrência -> erro, pois o ETL deveria garantir unicidade.
    """
    linhas = df[
        df["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq(str(codigo))
    ]

    if linhas.empty:
        return None

    if len(linhas) != 1:
        raise RuntimeError(
            f"Conta {codigo} encontrada {len(linhas)} vezes "
            "na mesma demonstração/exercício."
        )

    valor = linhas.iloc[0]["VL_CONTA"]

    if pd.isna(valor):
        return None

    return float(valor)


def _dividir(
    numerador: float | None,
    denominador: float | None,
    absoluto_denominador: bool = False,
) -> float | None:
    if numerador is None or denominador is None:
        return None

    if absoluto_denominador:
        denominador = abs(denominador)

    if denominador == 0:
        return None

    return numerador / denominador


def _somar(*valores: float | None) -> float | None:
    if any(v is None for v in valores):
        return None
    return float(sum(valores))


def _media(
    inicial: float | None,
    final: float | None,
) -> float | None:
    if inicial is None or final is None:
        return None
    return (inicial + final) / 2.0


def _pl_medio_ajustado(
    pl_inicial: float | None,
    pl_final: float | None,
    lucro_liquido: float | None,
) -> float | None:
    if (
        pl_inicial is None
        or pl_final is None
        or lucro_liquido is None
    ):
        return None

    return (
        pl_inicial
        + pl_final
        - lucro_liquido
    ) / 2.0


def _carregar_auxiliar_2022(
    cd_cvm: str,
) -> dict[str, float | None]:
    if not ARQUIVO_AUXILIAR.exists():
        raise FileNotFoundError(
            f"Arquivo auxiliar não encontrado: {ARQUIVO_AUXILIAR}. "
            "Execute primeiro: python src\\ano_auxiliar.py"
        )

    d = pd.read_parquet(ARQUIVO_AUXILIAR)
    cd_cvm = _normalizar_cd_cvm(cd_cvm)

    d = d[
        d["CD_CVM"]
        .astype(str)
        .str.zfill(6)
        .eq(cd_cvm)
    ].copy()

    ativo = d[
        (d["DEMONSTRACAO"] == "BPA")
        & (d["CD_CONTA"].astype(str) == "1")
    ]

    pl = d[
        (d["DEMONSTRACAO"] == "BPP")
        & (d["CD_CONTA"].astype(str) == "2.03")
    ]

    return {
        "AT": (
            float(ativo.iloc[0]["VL_CONTA"])
            if len(ativo) == 1
            else None
        ),
        "PL": (
            float(pl.iloc[0]["VL_CONTA"])
            if len(pl) == 1
            else None
        ),
    }


def _componentes_ano(
    cd_cvm: str,
    ano: int,
) -> dict[str, float | None]:
    bpa = carregar_demonstracao(
        cd_cvm,
        ano,
        "BPA",
    )

    bpp = carregar_demonstracao(
        cd_cvm,
        ano,
        "BPP",
    )

    dre = carregar_demonstracao(
        cd_cvm,
        ano,
        "DRE",
    )

    return {
        "AT": _valor_conta(bpa, "1"),
        "AC": _valor_conta(bpa, "1.01"),
        "DISP": _valor_conta(bpa, "1.01.01"),
        "APLIC": _valor_conta(bpa, "1.01.02"),
        "CR": _valor_conta(bpa, "1.01.03"),
        "RLP": _valor_conta(bpa, "1.02.01"),
        "INV": _valor_conta(bpa, "1.02.02"),
        "IMOB": _valor_conta(bpa, "1.02.03"),
        "INTANG": _valor_conta(bpa, "1.02.04"),
        "PC": _valor_conta(bpp, "2.01"),
        "EMP_CP": _valor_conta(bpp, "2.01.04"),
        "PNC": _valor_conta(bpp, "2.02"),
        "EMP_LP": _valor_conta(bpp, "2.02.01"),
        "PL": _valor_conta(bpp, "2.03"),
        "RECEITA": _valor_conta(dre, "3.01"),
        "EBIT": _valor_conta(dre, "3.05"),
        "DESP_FIN": _valor_conta(dre, "3.06.02"),
        "LL": _valor_conta(dre, "3.11"),
    }


def calcular_indicadores_ano(
    cd_cvm: str,
    ano: int,
    componentes_anteriores: dict[str, float | None] | None = None,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """
    Calcula os 12 indicadores do professor para um exercício.

    Percentuais são armazenados em forma decimal.
    Ex.: 0.25 = 25%.
    """
    c = _componentes_ano(
        cd_cvm,
        ano,
    )

    anterior = componentes_anteriores or {}

    ap = _somar(
        c["INV"],
        c["IMOB"],
        c["INTANG"],
    )

    capital_terceiros = _somar(
        c["PC"],
        c["PNC"],
    )

    passivo_financeiro = _somar(
        c["EMP_CP"],
        c["EMP_LP"],
    )

    ativo_liquido_seco = _somar(
        c["DISP"],
        c["APLIC"],
        c["CR"],
    )

    at_medio = _media(
        anterior.get("AT"),
        c["AT"],
    )

    pl_medio_ajustado = _pl_medio_ajustado(
        anterior.get("PL"),
        c["PL"],
        c["LL"],
    )

    indicadores = {
        "IPL": _dividir(
            ap,
            c["PL"],
        ),
        "PCT": _dividir(
            capital_terceiros,
            c["PL"],
        ),
        "CE": _dividir(
            c["PC"],
            capital_terceiros,
        ),
        "EFSAT": _dividir(
            passivo_financeiro,
            c["AT"],
        ),
        "LG": _dividir(
            _somar(
                c["AC"],
                c["RLP"],
            ),
            capital_terceiros,
        ),
        "LC": _dividir(
            c["AC"],
            c["PC"],
        ),
        "LS": _dividir(
            ativo_liquido_seco,
            c["PC"],
        ),
        "ICJ": _dividir(
            c["EBIT"],
            c["DESP_FIN"],
            absoluto_denominador=True,
        ),
        "GA": _dividir(
            c["RECEITA"],
            at_medio,
        ),
        "RSV": _dividir(
            c["LL"],
            c["RECEITA"],
        ),
        "ROA": _dividir(
            c["LL"],
            at_medio,
        ),
        "ROE": _dividir(
            c["LL"],
            pl_medio_ajustado,
        ),
    }

    componentes_auditaveis = {
        **c,
        "AP": ap,
        "CT": capital_terceiros,
        "PF": passivo_financeiro,
        "ATm": at_medio,
        "PLma": pl_medio_ajustado,
        "AT_inicial": anterior.get("AT"),
        "PL_inicial": anterior.get("PL"),
    }

    return indicadores, componentes_auditaveis


def calcular_indicadores(
    cd_cvm: str,
    anos: list[int] | None = None,
) -> pd.DataFrame:
    """
    Retorna tabela longa com os 12 indicadores por ano.
    """
    cd_cvm = _normalizar_cd_cvm(cd_cvm)

    disponiveis = anos_disponiveis(
        cd_cvm
    )

    if anos is None:
        anos_usados = disponiveis
    else:
        anos_usados = sorted(
            int(a)
            for a in anos
            if int(a) in disponiveis
        )

    if not anos_usados:
        return pd.DataFrame()

    primeiro_ano = min(anos_usados)

    if primeiro_ano == min(disponiveis):
        auxiliar = _carregar_auxiliar_2022(
            cd_cvm
        )
        componentes_anteriores = {
            "AT": auxiliar["AT"],
            "PL": auxiliar["PL"],
        }
    else:
        anterior_comp = _componentes_ano(
            cd_cvm,
            primeiro_ano - 1,
        )
        componentes_anteriores = {
            "AT": anterior_comp["AT"],
            "PL": anterior_comp["PL"],
        }

    linhas = []

    for ano in anos_usados:
        indicadores, componentes = (
            calcular_indicadores_ano(
                cd_cvm,
                ano,
                componentes_anteriores,
            )
        )

        for codigo, valor in indicadores.items():
            linhas.append(
                {
                    "CD_CVM": cd_cvm,
                    "ANO": ano,
                    "GRUPO": GRUPOS[codigo],
                    "INDICADOR": codigo,
                    "UNIDADE": UNIDADES[codigo],
                    "VALOR": valor,
                    "FORMULA": FORMULAS[codigo],
                }
            )

        componentes_anteriores = {
            "AT": componentes["AT"],
            "PL": componentes["PL"],
        }

    return pd.DataFrame(linhas)


def quadro_indicadores(
    cd_cvm: str,
    anos: list[int] | None = None,
) -> pd.DataFrame:
    """
    Formato de apresentação:
    Grupo | Indicador | Unidade | 2023 | 2024 | 2025
    """
    base = calcular_indicadores(
        cd_cvm,
        anos=anos,
    )

    if base.empty:
        return base

    valores = (
        base.pivot(
            index=[
                "GRUPO",
                "INDICADOR",
                "UNIDADE",
            ],
            columns="ANO",
            values="VALOR",
        )
        .reset_index()
    )

    ordem = [
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
        "ROA",
        "ROE",
    ]

    valores["_ORDEM"] = (
        valores["INDICADOR"]
        .map(
            {
                cod: i
                for i, cod in enumerate(ordem)
            }
        )
    )

    valores = (
        valores
        .sort_values("_ORDEM")
        .drop(columns="_ORDEM")
        .reset_index(drop=True)
    )

    valores.columns.name = None

    return valores


def detalhar_indicador(
    cd_cvm: str,
    ano: int,
    indicador: str,
) -> dict[str, object]:
    """
    Retorna fórmula, componentes e resultado utilizados no cálculo.
    """
    indicador = indicador.upper().strip()

    if indicador not in FORMULAS:
        raise ValueError(
            f"Indicador inválido: {indicador}"
        )

    cd_cvm = _normalizar_cd_cvm(cd_cvm)

    disponiveis = anos_disponiveis(
        cd_cvm
    )

    if ano not in disponiveis:
        raise ValueError(
            f"Ano {ano} não disponível para {cd_cvm}."
        )

    if ano == min(disponiveis):
        aux = _carregar_auxiliar_2022(
            cd_cvm
        )
        anterior = {
            "AT": aux["AT"],
            "PL": aux["PL"],
        }
    else:
        anterior_comp = _componentes_ano(
            cd_cvm,
            ano - 1,
        )
        anterior = {
            "AT": anterior_comp["AT"],
            "PL": anterior_comp["PL"],
        }

    valores, componentes = (
        calcular_indicadores_ano(
            cd_cvm,
            ano,
            anterior,
        )
    )

    return {
        "CD_CVM": cd_cvm,
        "ANO": ano,
        "INDICADOR": indicador,
        "GRUPO": GRUPOS[indicador],
        "UNIDADE": UNIDADES[indicador],
        "FORMULA": FORMULAS[indicador],
        "RESULTADO": valores[indicador],
        "COMPONENTES": componentes,
    }


def validar_dupont(
    cd_cvm: str,
    anos: list[int] | None = None,
    tolerancia: float = 1e-10,
) -> pd.DataFrame:
    """
    Valida a identidade DuPont:
        ROA = GA * RSV

    A checagem usa os valores não arredondados.
    """
    base = calcular_indicadores(
        cd_cvm,
        anos=anos,
    )

    if base.empty:
        return pd.DataFrame()

    pivo = base.pivot(
        index="ANO",
        columns="INDICADOR",
        values="VALOR",
    )

    linhas = []

    for ano, linha in pivo.iterrows():
        ga = linha.get("GA")
        rsv = linha.get("RSV")
        roa = linha.get("ROA")

        if (
            pd.isna(ga)
            or pd.isna(rsv)
            or pd.isna(roa)
        ):
            calculado = None
            diferenca = None
            status = "N/D"
        else:
            calculado = float(ga) * float(rsv)
            diferenca = float(roa) - calculado
            status = (
                "OK"
                if abs(diferenca) <= tolerancia
                else "ERRO"
            )

        linhas.append(
            {
                "ANO": int(ano),
                "GA": ga,
                "RSV": rsv,
                "ROA": roa,
                "GA_X_RSV": calculado,
                "DIFERENCA": diferenca,
                "STATUS": status,
            }
        )

    return pd.DataFrame(linhas)


def formatar_valor_indicador(
    indicador: str,
    valor: float | None,
) -> str:
    """
    Formatação textual para console/interface.
    """
    if valor is None or pd.isna(valor):
        return "N/D"

    indicador = indicador.upper().strip()

    if indicador in PERCENTUAIS:
        return f"{valor * 100:.2f}%"

    return f"{valor:.2f}"


def main() -> None:
    cd_cvm = "004170"
    anos = [2023, 2024, 2025]

    print("=" * 70)
    print("SISTEMA CVM - INDICADORES")
    print("=" * 70)

    quadro = quadro_indicadores(
        cd_cvm,
        anos=anos,
    )

    exibicao = quadro.copy()

    for coluna in anos:
        exibicao[coluna] = [
            formatar_valor_indicador(
                indicador,
                valor,
            )
            for indicador, valor
            in zip(
                exibicao["INDICADOR"],
                exibicao[coluna],
            )
        ]

    print()
    print("VALE S.A.")
    print(
        exibicao.to_string(
            index=False
        )
    )

    print()
    print("VALIDAÇÃO DUPONT")
    print(
        validar_dupont(
            cd_cvm,
            anos=anos,
        ).to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.catalogo_vigencias import (  # noqa: E402
    EvidenciaFcaTicker,
    ObservacaoIsin,
    _fim_por_evidencia,
    _inicio_por_evidencia,
    construir_catalogo_temporal,
)


def instrumento(i, cd, classe, inicio, fim="", status="ATIVO"):
    tipo = "UNIT" if classe == "UNIT" else "ACAO"
    return {
        "INSTRUMENTO_ID": str(i),
        "CD_CVM": cd,
        "TIPO_ATIVO": tipo,
        "CLASSE": classe,
        "MOEDA": "BRL",
        "DT_INICIO": inicio,
        "DT_FIM": fim,
        "STATUS": status,
        "FONTE": "FIXTURE",
    }


def ticker(i, codigo, inicio, fim="", status="VIGENTE"):
    return {
        "INSTRUMENTO_ID": str(i),
        "BOLSA": "B3",
        "TICKER": codigo,
        "DT_INICIO": inicio,
        "DT_FIM": fim,
        "STATUS": status,
        "FONTE": "FIXTURE",
    }


def reconciliado(
    codigo,
    cd,
    classe,
    primeira,
    ultima,
    inicio_validado="",
    fim_validado="",
):
    tipo = "UNIT" if classe == "UNIT" else "ACAO"
    return {
        "TICKER": codigo,
        "CD_CVM": cd,
        "DENOM_CIA": "FIXTURE",
        "TIPO_ATIVO": tipo,
        "CLASSE": classe,
        "PRIMEIRA_DATA_2025": primeira,
        "ULTIMA_DATA_2025": ultima,
        "PREGOES_2025": "1",
        "ISINS_2025": "",
        "STATUS_FINAL": "RESOLVIDO",
        "FONTES": "FIXTURE",
        "VINCULO_EXCEPCIONAL": "",
        "DT_INICIO_VALIDADA": inicio_validado,
        "DT_FIM_VALIDADA": fim_validado,
        "PROBLEMAS": "",
    }


def alocacao(cd, classe, instrumento_id):
    tipo = "UNIT" if classe == "UNIT" else "ACAO"
    return {
        "CHAVE_CANDIDATO": f"{cd}|{tipo}|{classe}",
        "INSTRUMENTO_ID": str(instrumento_id),
    }


def evidencia(
    ano,
    codigo,
    cd,
    inicio=None,
    fim=None,
    referencia=None,
):
    return EvidenciaFcaTicker(
        ano=ano,
        ticker=codigo,
        cd_cvm=cd,
        data_referencia=referencia or date(ano, 12, 31),
        versao=1,
        data_inicio_negociacao=inicio,
        data_fim_negociacao=fim,
        data_inicio_listagem=None,
        data_fim_listagem=None,
    )


def teste_limites_fca_vs_cotahist():
    base = reconciliado(
        "TEST3", "000001", "ON",
        "2025-02-14", "2025-12-30"
    )

    # Início FCA posterior à negociação observada: COTAHIST prevalece.
    evid = [
        evidencia(
            2025, "TEST3", "000001",
            date(2025, 2, 17), None
        )
    ]
    inicio, origem = _inicio_por_evidencia(
        linha_ticker=base,
        evidencias=evid,
    )
    assert inicio == date(2025, 2, 14)
    assert origem == "COTAHIST_2025_CORRECAO_LIMITE_FCA"

    # Fim FCA igual à última negociação observada vira fim exclusivo +1 dia.
    base_fim = reconciliado(
        "TEST3", "000001", "ON",
        "2025-01-02", "2025-09-22"
    )
    evid_fim = [
        evidencia(
            2025, "TEST3", "000001",
            date(2020, 1, 1), date(2025, 9, 22)
        )
    ]
    fim, fonte = _fim_por_evidencia(
        linha_ticker=base_fim,
        evidencias=evid_fim,
    )
    assert fim == date(2025, 9, 23)
    assert fonte == "FCA_FIM_INCLUSIVO_NORMALIZADO"

    # Fim FCA anterior ao COTAHIST observado é tratado como metadado
    # desatualizado e não trunca a série.
    base_stale = reconciliado(
        "TEST3", "000001", "ON",
        "2025-01-02", "2025-11-13"
    )
    evid_stale = [
        evidencia(
            2025, "TEST3", "000001",
            date(2020, 1, 1), date(2025, 11, 4)
        )
    ]
    fim_stale, _ = _fim_por_evidencia(
        linha_ticker=base_stale,
        evidencias=evid_stale,
    )
    assert fim_stale is None


def main():
    print("=" * 88)
    print("SISTEMA CVM — TESTE D.4 — VIGÊNCIAS DE TICKER/ISIN")
    print("=" * 88)

    teste_limites_fca_vs_cotahist()

    existentes = [
        instrumento(3001, "002437", "ON", "2010-01-01"),
        instrumento(
            5001, "019550", "ON",
            "2010-01-01", "2019-12-18", "ENCERRADO"
        ),
        instrumento(
            5003, "019550", "ON",
            "2025-07-02"
        ),
    ]
    candidatos = existentes + [
        instrumento(5004, "002437", "PNA", "2025-01-02"),
    ]
    tickers_existentes = [
        ticker(3001, "ELET3", "2010-01-01", "2025-11-10", "ENCERRADO"),
        ticker(3001, "AXIA3", "2025-11-10"),
        ticker(5001, "NATU3", "2010-01-01", "2019-12-18", "ENCERRADO"),
        ticker(5003, "NATU3", "2025-07-02"),
    ]

    reconciliados = [
        reconciliado(
            "ELET3", "002437", "ON",
            "2025-01-02", "2025-11-07"
        ),
        reconciliado(
            "AXIA3", "002437", "ON",
            "2025-11-10", "2025-12-30", "2025-11-10"
        ),
        reconciliado(
            "NATU3", "019550", "ON",
            "2025-07-02", "2025-12-30", "2025-07-02"
        ),
        reconciliado(
            "ELET5", "002437", "PNA",
            "2025-01-02", "2025-11-07"
        ),
        reconciliado(
            "AXIA5", "002437", "PNA",
            "2025-11-10", "2025-12-30", "2025-11-10"
        ),
    ]

    evidencias = [
        evidencia(
            2025, "ELET5", "002437",
            date(1995, 1, 1), date(2025, 11, 10)
        ),
        evidencia(
            2026, "AXIA5", "002437",
            date(2025, 11, 10), None
        ),
        # NATU3 antigo existe no FCA, mas o ID 5003 já possui sua
        # vigência própria e não pode ser colado ao 5001.
        evidencia(
            2019, "NATU3", "019550",
            date(2004, 5, 26), date(2019, 12, 18)
        ),
        evidencia(
            2026, "NATU3", "019550",
            date(2025, 7, 2), None
        ),
    ]

    observacoes = [
        ObservacaoIsin(date(2025, 11, 7), "ELET5", "BRELETPREFX1"),
        ObservacaoIsin(date(2025, 11, 10), "AXIA5", "BRAXIAPREFX2"),
        ObservacaoIsin(date(2025, 12, 30), "AXIA5", "BRAXIAPREFX2"),
        ObservacaoIsin(date(2025, 7, 2), "NATU3", "BRNATUACNOR6"),
    ]

    resultado = construir_catalogo_temporal(
        instrumentos_existentes=existentes,
        instrumentos_candidatos=candidatos,
        tickers_existentes=tickers_existentes,
        identificadores_existentes=[],
        alocacoes=[
            alocacao("002437", "ON", 3001),
            alocacao("019550", "ON", 5003),
            alocacao("002437", "PNA", 5004),
        ],
        tickers_reconciliados_2025=reconciliados,
        evidencias_fca=evidencias,
        observacoes_isin=observacoes,
    )

    assert resultado.gate_aprovado is True
    assert resultado.revisao == []

    instrumentos = {
        int(x["INSTRUMENTO_ID"]): x
        for x in resultado.instrumentos
    }
    assert instrumentos[3001] == existentes[0]
    assert instrumentos[5001] == existentes[1]
    assert instrumentos[5003] == existentes[2]
    assert instrumentos[5004]["DT_INICIO"] == "2010-01-01"

    pna = [
        x for x in resultado.tickers
        if int(x["INSTRUMENTO_ID"]) == 5004
    ]
    pna_por_codigo = {x["TICKER"]: x for x in pna}
    assert pna_por_codigo["ELET5"]["DT_FIM"] == "2025-11-10"
    assert pna_por_codigo["AXIA5"]["DT_INICIO"] == "2025-11-10"

    # O NATU3 antigo continua separado do NATU3 atual.
    natu = [
        x for x in resultado.tickers
        if x["TICKER"] == "NATU3"
    ]
    assert {int(x["INSTRUMENTO_ID"]) for x in natu} == {5001, 5003}

    isins_5004 = [
        x for x in resultado.identificadores
        if int(x["INSTRUMENTO_ID"]) == 5004
    ]
    assert len(isins_5004) == 2
    assert isins_5004[0]["DT_FIM"] == "2025-11-10"
    assert isins_5004[1]["DT_INICIO"] == "2025-11-10"

    print("RESULTADO: APROVADO")
    print("Instrumentos piloto preservados: aprovado")
    print("FCA retrocede vigência analítica sem renumerar ID: aprovado")
    print("Ticker sucessor fecha intervalo anterior em [início,fim): aprovado")
    print("NATU3 antigo/atual permanecem separados: aprovado")
    print("ISIN observado é temporal e não redefine identidade: aprovado")


if __name__ == "__main__":
    main()

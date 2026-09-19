from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.catalogo_ampliado import gerar_catalogo_ampliado  # noqa: E402


def instrumento(
    instrumento_id,
    cd_cvm,
    tipo,
    classe,
    inicio,
    fim="",
    status="ATIVO",
):
    return {
        "INSTRUMENTO_ID": str(instrumento_id),
        "CD_CVM": cd_cvm,
        "TIPO_ATIVO": tipo,
        "CLASSE": classe,
        "MOEDA": "BRL",
        "DT_INICIO": inicio,
        "DT_FIM": fim,
        "STATUS": status,
        "FONTE": "FIXTURE",
    }


def grupo(cd_cvm, tipo, classe, inicio, fim, tickers):
    return {
        "CHAVE_CANDIDATO": f"{cd_cvm}|{tipo}|{classe}",
        "CD_CVM": cd_cvm,
        "DENOM_CIA": "FIXTURE",
        "TIPO_ATIVO": tipo,
        "CLASSE": classe,
        "TICKERS_2025": tickers,
        "QTD_TICKERS_2025": str(len(tickers.split("|"))),
        "ISINS_2025": "",
        "PRIMEIRA_DATA_2025": inicio,
        "ULTIMA_DATA_2025": fim,
        "STATUS": "CANDIDATO_APROVADO",
        "PROBLEMAS": "",
    }


def fixtures_existentes():
    return [
        instrumento(3001, "002437", "ACAO", "ON", "2010-01-01"),
        instrumento(
            5001, "019550", "ACAO", "ON",
            "2010-01-01", "2019-12-18", "ENCERRADO"
        ),
        instrumento(
            5002, "024783", "ACAO", "ON",
            "2019-12-18", "2025-07-02", "ENCERRADO"
        ),
        instrumento(5003, "019550", "ACAO", "ON", "2025-07-02"),
    ]


def fixtures_grupos():
    return [
        grupo(
            "002437", "ACAO", "ON",
            "2025-01-02", "2025-12-30", "ELET3|AXIA3"
        ),
        grupo(
            "024783", "ACAO", "ON",
            "2025-01-02", "2025-07-01", "NTCO3"
        ),
        grupo(
            "019550", "ACAO", "ON",
            "2025-07-02", "2025-12-30", "NATU3"
        ),
        grupo(
            "002437", "ACAO", "PNA",
            "2025-01-02", "2025-12-30", "ELET5|AXIA5"
        ),
    ]


def teste_preserva_e_reutiliza_por_vigencia():
    existentes = fixtures_existentes()
    resultado = gerar_catalogo_ampliado(
        existentes,
        fixtures_grupos(),
    )

    assert resultado.gate_aprovado is True
    assert resultado.revisao == []

    mapa = {
        x["CHAVE_CANDIDATO"]: (
            int(x["INSTRUMENTO_ID"]),
            x["ORIGEM_ID"],
        )
        for x in resultado.alocacoes
    }

    assert mapa["002437|ACAO|ON"] == (3001, "REUTILIZADO")
    assert mapa["024783|ACAO|ON"] == (5002, "REUTILIZADO")
    assert mapa["019550|ACAO|ON"] == (5003, "REUTILIZADO")
    assert mapa["002437|ACAO|PNA"] == (5004, "NOVO")

    antigos = {
        int(x["INSTRUMENTO_ID"]): x
        for x in existentes
    }
    finais = {
        int(x["INSTRUMENTO_ID"]): x
        for x in resultado.instrumentos
    }

    # 5001 continua intacto e nao e confundido com NATU3 atual.
    assert finais[5001] == antigos[5001]
    assert finais[5003] == antigos[5003]


def teste_alocacao_independe_da_ordem():
    a = gerar_catalogo_ampliado(
        fixtures_existentes(),
        fixtures_grupos(),
    )
    b = gerar_catalogo_ampliado(
        fixtures_existentes(),
        list(reversed(fixtures_grupos())),
    )

    mapa_a = {
        x["CHAVE_CANDIDATO"]: x["INSTRUMENTO_ID"]
        for x in a.alocacoes
    }
    mapa_b = {
        x["CHAVE_CANDIDATO"]: x["INSTRUMENTO_ID"]
        for x in b.alocacoes
    }

    assert mapa_a == mapa_b


def teste_ambiguidade_bloqueia():
    existentes = fixtures_existentes() + [
        instrumento(7001, "002437", "ACAO", "ON", "2024-01-01"),
    ]
    resultado = gerar_catalogo_ampliado(
        existentes,
        [
            grupo(
                "002437", "ACAO", "ON",
                "2025-01-02", "2025-12-30", "ELET3|AXIA3"
            )
        ],
    )

    assert resultado.gate_aprovado is False
    assert len(resultado.alocacoes) == 0
    assert any(
        "MULTIPLOS_IDS_EXISTENTES_SOBREPOSTOS" in x["DETALHE"]
        for x in resultado.revisao
    )


def main():
    print("=" * 82)
    print("SISTEMA CVM — TESTE D.4 — CATÁLOGO AMPLIADO / IDs ESTÁVEIS")
    print("=" * 82)

    teste_preserva_e_reutiliza_por_vigencia()
    teste_alocacao_independe_da_ordem()
    teste_ambiguidade_bloqueia()

    print("RESULTADO: APROVADO")
    print("IDs existentes preservados: aprovado")
    print("Reuso temporal sem fundir NATU3 antigo/atual: aprovado")
    print("Novos IDs determinísticos acima do máximo atual: aprovado")
    print("Ambiguidade de identidade: bloqueada")


if __name__ == "__main__":
    main()

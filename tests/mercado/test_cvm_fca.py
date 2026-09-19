from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.providers.cvm_fca import (  # noqa: E402
    ler_fca_valores_mobiliarios,
    ticker_formato_elegivel,
)


def _zip_fixture(caminho: Path) -> None:
    principal = (
        "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC\n"
        "33.000.167/0001-01;2025-01-01;1;PETROLEO BRASILEIRO S.A.;009512;FCA;1;2025-01-02;x\n"
        "07.859.971/0001-30;2025-01-01;1;TAESA;020257;FCA;2;2025-01-02;x\n"
    )
    vm = (
        "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Empresarial;"
        "Valor_Mobiliario;Sigla_Classe_Acao_Preferencial;Classe_Acao_Preferencial;"
        "Codigo_Negociacao;Composicao_BDR_Unit;Mercado;Sigla_Entidade_Administradora;"
        "Entidade_Administradora;Data_Inicio_Negociacao;Data_Fim_Negociacao;"
        "Segmento;Data_Inicio_Listagem;Data_Fim_Listagem\n"
        "33.000.167/0001-01;2025-01-01;1;1;PETROBRAS;Ações;;;PETR3;;Bolsa;B3;"
        "B3;2000-01-01;;Nível 2;2000-01-01;\n"
        "33.000.167/0001-01;2025-01-01;1;1;PETROBRAS;Ações;PN;Preferencial;"
        "PETR4;;Bolsa;B3;B3;2000-01-01;;Nível 2;2000-01-01;\n"
        "07.859.971/0001-30;2025-01-01;1;2;TAESA;Units;;;TAEE11;1 ON + 2 PN;"
        "Bolsa;B3;B3;2006-01-01;;Nível 2;2006-01-01;\n"
    )

    with ZipFile(caminho, "w") as zf:
        zf.writestr("fca_cia_aberta_2025.csv", principal.encode("latin-1"))
        zf.writestr(
            "fca_cia_aberta_valor_mobiliario_2025.csv",
            vm.encode("latin-1"),
        )


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.4 — PROVIDER CVM FCA")
    print("=" * 72)

    assert ticker_formato_elegivel("PETR3")
    assert ticker_formato_elegivel("PETR4")
    assert ticker_formato_elegivel("TAEE11")
    assert ticker_formato_elegivel("B3SA3")
    assert not ticker_formato_elegivel("AMAR1")
    assert not ticker_formato_elegivel("AMAR9")
    assert not ticker_formato_elegivel("4030")

    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "fca_cia_aberta_2025.zip"
        _zip_fixture(caminho)

        linhas, ambiguos = ler_fca_valores_mobiliarios(
            caminho,
            ano=2025,
        )

    assert ambiguos == {}
    assert len(linhas) == 3

    por_ticker = {linha.codigo_negociacao: linha for linha in linhas}
    assert por_ticker["PETR3"].cd_cvm == "009512"
    assert por_ticker["PETR4"].cd_cvm == "009512"
    assert por_ticker["TAEE11"].cd_cvm == "020257"
    assert por_ticker["TAEE11"].composicao_bdr_unit == "1 ON + 2 PN"

    print("RESULTADO: APROVADO")
    print("FCA ZIP + CSV latin-1: aprovado")
    print("CNPJ -> CD_CVM: aprovado")
    print("ticker ação/unit: aprovado")
    print("códigos de direito/recibo inválidos: rejeitados")


if __name__ == "__main__":
    main()

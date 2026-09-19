from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.promocao_catalogo import (  # noqa: E402
    promover_catalogo,
    sha256_arquivo,
)


def _escrever(path: Path, campos: list[str], linhas: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(linhas)


def _montar(dir_: Path, *, candidato: bool) -> None:
    instrumentos = [
        {
            "INSTRUMENTO_ID": "1",
            "CD_CVM": "000001",
            "TIPO_ATIVO": "ACAO",
            "CLASSE": "ON",
            "MOEDA": "BRL",
            "DT_INICIO": "2020-01-01",
            "DT_FIM": "",
            "STATUS": "ATIVO",
            "FONTE": "FIXTURE",
        }
    ]
    tickers = [
        {
            "INSTRUMENTO_ID": "1",
            "BOLSA": "B3",
            "TICKER": "TEST3",
            "DT_INICIO": "2020-01-01",
            "DT_FIM": "",
            "STATUS": "VIGENTE",
            "FONTE": "FIXTURE",
        }
    ]
    identificadores = []

    if candidato:
        instrumentos.append(
            {
                "INSTRUMENTO_ID": "2",
                "CD_CVM": "000002",
                "TIPO_ATIVO": "ACAO",
                "CLASSE": "PN",
                "MOEDA": "BRL",
                "DT_INICIO": "2021-01-01",
                "DT_FIM": "",
                "STATUS": "ATIVO",
                "FONTE": "FIXTURE",
            }
        )
        tickers.append(
            {
                "INSTRUMENTO_ID": "2",
                "BOLSA": "B3",
                "TICKER": "TSTB4",
                "DT_INICIO": "2021-01-01",
                "DT_FIM": "",
                "STATUS": "VIGENTE",
                "FONTE": "FIXTURE",
            }
        )

    _escrever(
        dir_ / "instrumentos.csv",
        [
            "INSTRUMENTO_ID", "CD_CVM", "TIPO_ATIVO", "CLASSE",
            "MOEDA", "DT_INICIO", "DT_FIM", "STATUS", "FONTE",
        ],
        instrumentos,
    )
    _escrever(
        dir_ / "tickers_historico.csv",
        [
            "INSTRUMENTO_ID", "BOLSA", "TICKER", "DT_INICIO",
            "DT_FIM", "STATUS", "FONTE",
        ],
        tickers,
    )
    _escrever(
        dir_ / "identificadores.csv",
        [
            "INSTRUMENTO_ID", "TIPO_IDENTIFICADOR", "VALOR",
            "DT_INICIO", "DT_FIM", "FONTE",
        ],
        identificadores,
    )


def main() -> None:
    print("=" * 82)
    print("SISTEMA CVM — TESTE D.4 — PROMOÇÃO CONTROLADA DO CATÁLOGO")
    print("=" * 82)

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        referencia = raiz / "reference"
        candidato = raiz / "candidate"
        referencia.mkdir()
        candidato.mkdir()

        _montar(referencia, candidato=False)
        _montar(candidato, candidato=True)

        protegido = raiz / "protegido.duckdb"
        protegido.write_bytes(b"nao-alterar")
        hash_antes = sha256_arquivo(protegido)

        resumo = promover_catalogo(
            candidate_dir=candidato,
            reference_dir=referencia,
            contagens_esperadas={
                "instrumentos": 2,
                "tickers": 2,
                "identificadores": 0,
            },
            caminhos_protegidos=(protegido,),
        )

        assert resumo.instrumentos == 2
        assert resumo.tickers == 2
        assert resumo.novos_ids == 1
        assert resumo.menor_novo_id == 2
        assert resumo.maior_novo_id == 2
        assert sha256_arquivo(protegido) == hash_antes
        for nome in (
            "instrumentos.csv",
            "tickers_historico.csv",
            "identificadores.csv",
        ):
            assert sha256_arquivo(referencia / nome) == sha256_arquivo(
                candidato / nome
            )

    print("RESULTADO: APROVADO")
    print("Preservação do catálogo-base: aprovada")
    print("Novos IDs incrementais: aprovados")
    print("Promoção + validação pós-escrita: aprovadas")
    print("Arquivo protegido por hash: inalterado")


if __name__ == "__main__":
    main()

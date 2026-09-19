from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.diagnostico_historico import (  # noqa: E402
    diagnosticar_ano,
    escrever_diagnostico,
)
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
)


ANO = 2023
REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
COTAHIST = (
    ROOT_DIR
    / "data"
    / "market"
    / "raw"
    / "b3"
    / "cotahist"
    / str(ANO)
    / f"COTAHIST_A{ANO}.ZIP"
)
SAIDA_DIR = (
    ROOT_DIR
    / "data"
    / "market"
    / "reports"
    / "d5_historico"
    / str(ANO)
)
SAIDA = SAIDA_DIR / f"diagnostico_identidade_{ANO}.csv"
PENDENTES = SAIDA_DIR / f"pendentes_identidade_{ANO}.csv"


def _catalogo_sistema() -> set[str]:
    con = conectar_cvm(read_only=True)
    try:
        return {
            str(x[0]).strip().zfill(6)
            for x in con.execute(
                "SELECT CD_CVM FROM empresas"
            ).fetchall()
        }
    finally:
        con.close()


def _escrever_pendentes(linhas: list[dict[str, str]]) -> None:
    pendentes = [
        x
        for x in linhas
        if x["STATUS"] != "RESOLVIDO_CATALOGO"
        and x["STATUS"] != "FORA_UNIVERSO_SISTEMA_FCA"
    ]
    if not pendentes:
        PENDENTES.parent.mkdir(parents=True, exist_ok=True)
        PENDENTES.write_text("", encoding="utf-8")
        return

    with PENDENTES.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=list(pendentes[0]),
            delimiter=";",
        )
        escritor.writeheader()
        escritor.writerows(pendentes)


def main() -> None:
    if not COTAHIST.is_file():
        raise FileNotFoundError(
            f"COTAHIST {ANO} não encontrado em {COTAHIST}"
        )

    print("=" * 100)
    print(
        f"SISTEMA CVM — D.5 — DIAGNÓSTICO HISTÓRICO DE IDENTIDADE — {ANO}"
    )
    print("=" * 100)
    print(f"COTAHIST: {COTAHIST}")
    print("Carregando FCA do mesmo ano...")

    fca_zip = baixar_fca(ANO)
    registros_fca, ambiguos = ler_fca_valores_mobiliarios(
        fca_zip,
        ano=ANO,
    )

    print(f"Registros FCA processados: {len(registros_fca):,}")
    print(f"CNPJ ambíguos no FCA {ANO}: {len(ambiguos):,}")
    print("Lendo COTAHIST e comparando com o catálogo promovido...")

    linhas = diagnosticar_ano(
        caminho_cotahist=COTAHIST,
        ano=ANO,
        reference_dir=REFERENCE_DIR,
        registros_fca=registros_fca,
        cd_cvm_sistema=_catalogo_sistema(),
    )

    escrever_diagnostico(SAIDA, linhas)
    _escrever_pendentes(linhas)

    contagem = Counter(x["STATUS"] for x in linhas)
    total = len(linhas)
    resolvidos = contagem["RESOLVIDO_CATALOGO"]
    candidatos = sum(
        qtd
        for status, qtd in contagem.items()
        if status.startswith("CANDIDATO_")
    )
    bloqueios = sum(
        qtd
        for status, qtd in contagem.items()
        if status.startswith("BLOQUEIO_")
    )
    sem_evidencia = contagem["SEM_EVIDENCIA_SUFICIENTE"]
    fora = contagem["FORA_UNIVERSO_SISTEMA_FCA"]

    print()
    print("RESUMO")
    print("-" * 100)
    print(f"Tickers elegíveis observados em {ANO}: {total:,}")
    print(f"Já resolvidos pelo catálogo temporal: {resolvidos:,}")
    print(f"Candidatos de identidade histórica: {candidatos:,}")
    print(f"Fora do universo contábil via FCA: {fora:,}")
    print(f"Sem evidência suficiente: {sem_evidencia:,}")
    print(f"Bloqueios/ambiguidades: {bloqueios:,}")
    print()
    print("STATUS")
    print("-" * 100)
    for status, qtd in sorted(contagem.items()):
        print(f"{status:<36} | {qtd:>5,}")

    print()
    print(f"Diagnóstico completo: {SAIDA}")
    print(f"Pendentes/candidatos: {PENDENTES}")
    print()
    print("RESULTADO: DIAGNÓSTICO GERADO")
    print(
        "Nenhum CSV oficial e nenhum banco foram alterados. "
        "Não promover identidades ainda."
    )


if __name__ == "__main__":
    main()

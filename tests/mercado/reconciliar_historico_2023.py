from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.banco import conectar as conectar_cvm  # noqa: E402
from src.mercado.reconciliacao_historica import (  # noqa: E402
    ler_csv_semicolon,
    reconciliar_diagnostico,
    serializar_resultados,
    escrever_csv_semicolon,
)
from src.mercado.providers.cvm_fca import (  # noqa: E402
    baixar_fca,
    ler_fca_valores_mobiliarios,
)


ANO = 2023
ANOS_FCA = (2022, 2023, 2024)
REFERENCE_DIR = ROOT_DIR / "data" / "reference" / "mercado"
REPORT_DIR = ROOT_DIR / "data" / "market" / "reports" / "d5_historico" / str(ANO)
DIAGNOSTICO = REPORT_DIR / f"diagnostico_identidade_{ANO}.csv"
SAIDA = REPORT_DIR / f"reconciliacao_identidade_{ANO}.csv"


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def _catalogo_sistema() -> set[str]:
    con = conectar_cvm(read_only=True)
    try:
        return {
            str(x[0]).strip().zfill(6)
            for x in con.execute("SELECT CD_CVM FROM empresas").fetchall()
        }
    finally:
        con.close()


def main() -> None:
    if not DIAGNOSTICO.is_file():
        raise FileNotFoundError(
            f"Execute primeiro diagnostico_historico_{ANO}.py: {DIAGNOSTICO}"
        )

    print("=" * 104)
    print(f"SISTEMA CVM — D.5 — RECONCILIAÇÃO HISTÓRICA — {ANO}")
    print("=" * 104)
    print("Carregando FCA adjacente 2022–2024...")

    registros = {}
    for ano in ANOS_FCA:
        caminho = baixar_fca(ano)
        itens, ambiguos = ler_fca_valores_mobiliarios(caminho, ano=ano)
        registros[ano] = itens
        print(
            f"FCA {ano}: {len(itens):,} registros | "
            f"CNPJ ambíguos: {len(ambiguos):,}"
        )

    diagnostico = ler_csv_semicolon(DIAGNOSTICO)
    instrumentos = _ler_csv(REFERENCE_DIR / "instrumentos.csv")

    resultados = reconciliar_diagnostico(
        diagnostico=diagnostico,
        instrumentos=instrumentos,
        registros_fca_por_ano=registros,
        cd_cvm_sistema=_catalogo_sistema(),
    )
    linhas = serializar_resultados(resultados)
    escrever_csv_semicolon(SAIDA, linhas)

    contagem = Counter(x.status for x in resultados)

    fortes = contagem["ALIAS_EXISTENTE_FORTE"]
    novos = contagem["NOVO_INSTRUMENTO_HISTORICO_CANDIDATO"]
    revisoes = sum(
        qtd
        for status, qtd in contagem.items()
        if status.startswith("REVISAO_")
    )
    sem_evidencia = contagem["SEM_EVIDENCIA_SUFICIENTE"]

    print()
    print("RESUMO")
    print("-" * 104)
    print(f"Total classificado: {len(resultados):,}")
    print(f"Já resolvidos existentes: {contagem['RESOLVIDO_EXISTENTE']:,}")
    print(f"Aliases históricos com evidência forte: {fortes:,}")
    print(f"Novos instrumentos históricos candidatos: {novos:,}")
    print(f"Fora do universo contábil: {contagem['FORA_UNIVERSO_SISTEMA']:,}")
    print(f"Revisões necessárias: {revisoes:,}")
    print(f"Sem evidência suficiente: {sem_evidencia:,}")
    print()
    print("STATUS")
    print("-" * 104)
    for status, qtd in sorted(contagem.items()):
        print(f"{status:<44} | {qtd:>5,}")

    if novos:
        print()
        print("NOVOS INSTRUMENTOS HISTÓRICOS — CANDIDATOS")
        print("-" * 104)
        for x in resultados:
            if x.status == "NOVO_INSTRUMENTO_HISTORICO_CANDIDATO":
                print(
                    f"{x.ticker:<12} | {x.chave_instrumento:<24} | "
                    f"{x.fonte}"
                )

    if revisoes or sem_evidencia:
        print()
        print("PENDÊNCIAS")
        print("-" * 104)
        for x in resultados:
            if (
                x.status.startswith("REVISAO_")
                or x.status == "SEM_EVIDENCIA_SUFICIENTE"
            ):
                print(
                    f"{x.ticker:<12} | {x.status:<38} | "
                    f"{x.cd_cvm:<6} | {x.detalhe}"
                )

    print()
    print(f"Relatório: {SAIDA}")
    print("RESULTADO: RECONCILIAÇÃO CANDIDATA GERADA")
    print("Nenhum ID novo foi alocado e nenhum catálogo/banco foi alterado.")


if __name__ == "__main__":
    main()

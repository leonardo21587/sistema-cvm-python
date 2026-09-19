from __future__ import annotations

import csv
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.mercado.catalogo import carregar_catalogo_referencia
from src.mercado.schema import criar_schema_identidade


ARQUIVOS_CATALOGO = (
    "instrumentos.csv",
    "tickers_historico.csv",
    "identificadores.csv",
)


@dataclass(frozen=True)
class ResumoPromocaoCatalogo:
    instrumentos: int
    tickers: int
    identificadores: int
    novos_ids: int
    menor_novo_id: int | None
    maior_novo_id: int | None
    hashes_protegidos: dict[str, str]


def sha256_arquivo(caminho: str | Path) -> str:
    caminho = Path(caminho)
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def _linhas_exatas(caminho: Path) -> set[tuple[tuple[str, str], ...]]:
    return {
        tuple(linha.items())
        for linha in _ler_csv(caminho)
    }


def _validar_preservacao(
    reference_dir: Path,
    candidate_dir: Path,
) -> None:
    for nome in ARQUIVOS_CATALOGO:
        base = _linhas_exatas(reference_dir / nome)
        candidato = _linhas_exatas(candidate_dir / nome)
        ausentes = base - candidato
        if ausentes:
            raise RuntimeError(
                f"{nome}: {len(ausentes)} linha(s) do catálogo atual "
                "não foram preservadas exatamente."
            )


def _validar_ids_incrementais(
    reference_dir: Path,
    candidate_dir: Path,
) -> tuple[int, int | None, int | None]:
    base = _ler_csv(reference_dir / "instrumentos.csv")
    candidato = _ler_csv(candidate_dir / "instrumentos.csv")

    ids_base = {int(x["INSTRUMENTO_ID"]) for x in base}
    ids_candidato = {int(x["INSTRUMENTO_ID"]) for x in candidato}

    if len(ids_candidato) != len(candidato):
        raise RuntimeError("INSTRUMENTO_ID duplicado no catálogo candidato.")

    if not ids_base.issubset(ids_candidato):
        raise RuntimeError("Catálogo candidato perdeu INSTRUMENTO_ID existente.")

    novos = sorted(ids_candidato - ids_base)
    if not novos:
        return 0, None, None

    primeiro = max(ids_base) + 1 if ids_base else min(novos)
    esperado = list(range(primeiro, primeiro + len(novos)))
    if novos != esperado:
        raise RuntimeError(
            "Novos INSTRUMENTO_ID não são contíguos acima do maior ID atual."
        )

    return len(novos), novos[0], novos[-1]


def validar_catalogo_diretorio(
    diretorio: str | Path,
) -> dict[str, int]:
    diretorio = Path(diretorio)
    con = duckdb.connect(":memory:")
    try:
        criar_schema_identidade(con)
        resumo = carregar_catalogo_referencia(
            con,
            reference_dir=diretorio,
        )
    finally:
        con.close()

    return {
        "instrumentos": int(resumo["instrumentos"]),
        "tickers": int(resumo["tickers"]),
        "identificadores": int(resumo["identificadores"]),
    }


def promover_catalogo(
    *,
    candidate_dir: str | Path,
    reference_dir: str | Path,
    contagens_esperadas: dict[str, int],
    caminhos_protegidos: tuple[str | Path, ...] = (),
) -> ResumoPromocaoCatalogo:
    """
    Promove os três CSVs do catálogo com validação prévia e rollback em erro.

    A promoção não escreve em bancos DuckDB. Hashes dos caminhos protegidos
    são conferidos antes/depois para provar essa propriedade operacional.
    """
    candidate_dir = Path(candidate_dir)
    reference_dir = Path(reference_dir)

    for nome in ARQUIVOS_CATALOGO:
        if not (candidate_dir / nome).is_file():
            raise FileNotFoundError(candidate_dir / nome)
        if not (reference_dir / nome).is_file():
            raise FileNotFoundError(reference_dir / nome)

    resumo_candidato = validar_catalogo_diretorio(candidate_dir)
    if resumo_candidato != contagens_esperadas:
        raise RuntimeError(
            "Contagens do catálogo candidato divergentes: "
            f"{resumo_candidato} != {contagens_esperadas}"
        )

    _validar_preservacao(reference_dir, candidate_dir)
    novos_ids, menor_novo, maior_novo = _validar_ids_incrementais(
        reference_dir,
        candidate_dir,
    )

    protegidos = [
        Path(caminho)
        for caminho in caminhos_protegidos
        if Path(caminho).is_file()
    ]
    hashes_antes = {
        str(caminho): sha256_arquivo(caminho)
        for caminho in protegidos
    }

    with tempfile.TemporaryDirectory(
        prefix="sistema_cvm_promocao_catalogo_"
    ) as tmp:
        backup_dir = Path(tmp) / "backup"
        backup_dir.mkdir(parents=True)

        for nome in ARQUIVOS_CATALOGO:
            shutil.copy2(
                reference_dir / nome,
                backup_dir / nome,
            )

        substituidos: list[str] = []
        try:
            for nome in ARQUIVOS_CATALOGO:
                temporario = reference_dir / f".{nome}.promocao.tmp"
                shutil.copyfile(candidate_dir / nome, temporario)
                os.replace(temporario, reference_dir / nome)
                substituidos.append(nome)

            if validar_catalogo_diretorio(reference_dir) != resumo_candidato:
                raise RuntimeError(
                    "Catálogo promovido divergiu do candidato após escrita."
                )

            for nome in ARQUIVOS_CATALOGO:
                if (
                    sha256_arquivo(reference_dir / nome)
                    != sha256_arquivo(candidate_dir / nome)
                ):
                    raise RuntimeError(
                        f"{nome}: conteúdo promovido difere do candidato."
                    )

            hashes_depois = {
                str(caminho): sha256_arquivo(caminho)
                for caminho in protegidos
            }
            if hashes_depois != hashes_antes:
                raise RuntimeError(
                    "Arquivo protegido foi alterado durante a promoção."
                )

        except Exception:
            for nome in ARQUIVOS_CATALOGO:
                backup = backup_dir / nome
                if backup.is_file():
                    restauracao = reference_dir / f".{nome}.rollback.tmp"
                    shutil.copyfile(backup, restauracao)
                    os.replace(restauracao, reference_dir / nome)

            # Confirma que o rollback também produz um catálogo carregável.
            validar_catalogo_diretorio(reference_dir)
            raise

    return ResumoPromocaoCatalogo(
        instrumentos=resumo_candidato["instrumentos"],
        tickers=resumo_candidato["tickers"],
        identificadores=resumo_candidato["identificadores"],
        novos_ids=novos_ids,
        menor_novo_id=menor_novo,
        maior_novo_id=maior_novo,
        hashes_protegidos=hashes_antes,
    )

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import (
    ANOS_ANALISE,
    CHUNK_SIZE,
    CVM_DFP_BASE_URL,
    DEMONSTRACOES,
    RAW_DIR,
    REQUEST_TIMEOUT,
)


def montar_url(ano: int) -> str:
    return f"{CVM_DFP_BASE_URL}/dfp_cia_aberta_{ano}.zip"


def baixar_zip(ano: int, sobrescrever: bool = False) -> Path:
    pasta_zips = RAW_DIR / "zips"
    pasta_zips.mkdir(parents=True, exist_ok=True)

    destino = pasta_zips / f"dfp_cia_aberta_{ano}.zip"

    if destino.exists() and not sobrescrever:
        if zipfile.is_zipfile(destino):
            print(f"[OK] {ano}: ZIP já existente.")
            return destino

        print(f"[AVISO] {ano}: arquivo existente inválido.")
        destino.unlink()

    url = montar_url(ano)
    temporario = destino.with_suffix(".zip.part")

    print(f"[DOWNLOAD] {ano}")
    print(url)

    headers = {
        "User-Agent": "Sistema-CVM-Python/1.0"
    }

    try:
        with requests.get(
            url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
            headers=headers,
        ) as resposta:

            resposta.raise_for_status()

            total = int(
                resposta.headers.get("content-length", 0)
            )

            baixado = 0

            with open(temporario, "wb") as arquivo:

                for bloco in resposta.iter_content(
                    chunk_size=CHUNK_SIZE
                ):
                    if not bloco:
                        continue

                    arquivo.write(bloco)
                    baixado += len(bloco)

                    if total:
                        percentual = baixado / total * 100

                        print(
                            f"\r{percentual:6.2f}%",
                            end="",
                            flush=True,
                        )

        print()

        if not zipfile.is_zipfile(temporario):
            temporario.unlink(missing_ok=True)

            raise RuntimeError(
                f"{ano}: arquivo recebido não é ZIP válido."
            )

        temporario.replace(destino)

        tamanho_mb = destino.stat().st_size / (1024 ** 2)

        print(
            f"[OK] {ano}: {tamanho_mb:.2f} MB"
        )

        return destino

    except Exception:
        temporario.unlink(missing_ok=True)
        raise


def localizar_arquivo(
    nomes_zip: list[str],
    demonstracao: str,
    ano: int,
) -> str:

    esperado = (
        f"_{demonstracao}_con_{ano}.csv"
    ).lower()

    encontrados = [
        nome
        for nome in nomes_zip
        if nome.lower().endswith(esperado)
    ]

    if len(encontrados) != 1:
        raise RuntimeError(
            f"{ano}: esperado 1 arquivo "
            f"{demonstracao}_con; "
            f"encontrados {len(encontrados)}."
        )

    return encontrados[0]


def extrair_demonstracoes(
    zip_path: Path,
    ano: int,
) -> list[Path]:

    destino = RAW_DIR / str(ano)
    destino.mkdir(parents=True, exist_ok=True)

    extraidos = []

    with zipfile.ZipFile(
        zip_path,
        "r",
    ) as arquivo_zip:

        nomes = arquivo_zip.namelist()

        for demonstracao in DEMONSTRACOES:

            membro = localizar_arquivo(
                nomes,
                demonstracao,
                ano,
            )

            nome_saida = Path(membro).name
            caminho_saida = destino / nome_saida

            with arquivo_zip.open(membro) as origem:
                with open(
                    caminho_saida,
                    "wb",
                ) as saida:
                    saida.write(origem.read())

            extraidos.append(caminho_saida)

            tamanho_mb = (
                caminho_saida.stat().st_size
                / (1024 ** 2)
            )

            print(
                f"[EXTRAÍDO] "
                f"{ano} | "
                f"{demonstracao} | "
                f"{tamanho_mb:.2f} MB"
            )

    return extraidos


def validar_ano(ano: int) -> None:

    pasta = RAW_DIR / str(ano)

    faltantes = []

    for demonstracao in DEMONSTRACOES:

        esperado = pasta / (
            f"dfp_cia_aberta_"
            f"{demonstracao}_con_{ano}.csv"
        )

        if (
            not esperado.exists()
            or esperado.stat().st_size == 0
        ):
            faltantes.append(demonstracao)

    if faltantes:
        raise RuntimeError(
            f"{ano}: arquivos ausentes: "
            + ", ".join(faltantes)
        )

    print(
        f"[VALIDADO] {ano}: "
        "BPA + BPP + DRE."
    )


def preparar_dados_cvm() -> None:

    print("=" * 60)
    print("SISTEMA CVM - DOWNLOAD DAS DFP")
    print("=" * 60)

    for ano in ANOS_ANALISE:

        print(f"\n--- {ano} ---")

        zip_path = baixar_zip(ano)

        extrair_demonstracoes(
            zip_path,
            ano,
        )

        validar_ano(ano)

    print("\n" + "=" * 60)

    print(
        "DOWNLOAD E EXTRAÇÃO "
        "CONCLUÍDOS COM SUCESSO"
    )

    print("=" * 60)

    print("\nArquivos em:")
    print(RAW_DIR)


if __name__ == "__main__":
    preparar_dados_cvm()
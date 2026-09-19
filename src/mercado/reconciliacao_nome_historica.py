from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from src.mercado.providers.b3_cotahist import iterar_cotacoes


def normalizar_nome_b3(valor: object) -> str:
    texto = str(valor or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        ch for ch in texto
        if not unicodedata.combining(ch)
    )
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return " ".join(texto.split())


def extrair_nomes_ticker_ano(
    *,
    caminhos_por_ano: dict[int, Path],
    tickers_por_ano: dict[int, set[str]],
) -> dict[tuple[int, str], tuple[str, ...]]:
    """
    Faz uma varredura leve dos COTAHISTs e retém somente NOME_RESUMIDO
    dos tickers já presentes no inventário histórico.
    """
    saida: dict[tuple[int, str], set[str]] = defaultdict(set)

    for ano in sorted(caminhos_por_ano):
        caminho = caminhos_por_ano[ano]
        alvos = {
            x.strip().upper()
            for x in tickers_por_ano.get(ano, set())
        }
        if not alvos:
            continue

        for cotacao in iterar_cotacoes(caminho):
            if cotacao.tipo_mercado != "010":
                continue
            ticker = cotacao.ticker.strip().upper()
            if ticker not in alvos:
                continue

            nome = normalizar_nome_b3(cotacao.nome_resumido)
            if nome:
                saida[(ano, ticker)].add(nome)

    return {
        chave: tuple(sorted(nomes))
        for chave, nomes in saida.items()
    }


def _cd_cvm_da_linha(
    linha: dict[str, str],
    instrumento_para_cd: dict[str, str],
) -> tuple[str, str] | None:
    status = linha.get("STATUS", "").strip().upper()

    if status in {"RESOLVIDO_EXISTENTE", "ALIAS_EXISTENTE_FORTE"}:
        instrumento_id = linha.get("INSTRUMENTO_ID", "").strip()
        cd = instrumento_para_cd.get(instrumento_id, "")
        if cd:
            return ("SISTEMA", cd)

    if status == "NOVO_INSTRUMENTO_HISTORICO_CANDIDATO":
        chave = linha.get("CHAVE_INSTRUMENTO", "").strip()
        partes = chave.split("|")
        if len(partes) == 3 and partes[0]:
            return ("SISTEMA", partes[0])

    if status == "FORA_UNIVERSO_SISTEMA":
        cd = linha.get("CD_CVM", "").strip()
        if cd and "|" not in cd:
            return ("FORA", cd)

    return None


def reconciliar_por_nome_b3(
    *,
    inventario: Iterable[dict[str, str]],
    nomes_por_ticker_ano: dict[tuple[int, str], tuple[str, ...]],
    instrumento_para_cd: dict[str, str],
    instrumentos_por_chave: dict[tuple[str, str, str], set[str]],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """
    Resolve pendências somente quando NOME_RESUMIDO exato aponta para uma
    única companhia ancorada no histórico.

    A resolução é por companhia primeiro. TIPO_ATIVO + CLASSE definem se
    há um instrumento existente ou um novo instrumento histórico candidato.
    """
    inventario = [dict(x) for x in inventario]

    empresas_por_nome: dict[str, set[tuple[str, str]]] = defaultdict(set)
    evidencias_por_nome: dict[str, int] = defaultdict(int)

    for linha in inventario:
        token = _cd_cvm_da_linha(linha, instrumento_para_cd)
        if token is None:
            continue

        chave = (int(linha["ANO"]), linha["TICKER"].strip().upper())
        for nome in nomes_por_ticker_ano.get(chave, ()):
            empresas_por_nome[nome].add(token)
            evidencias_por_nome[nome] += 1

    conflitos_nomes = [
        {
            "NOME_RESUMIDO": nome,
            "COMPANHIAS": "|".join(
                f"{tipo}:{cd}"
                for tipo, cd in sorted(tokens)
            ),
            "EVIDENCIAS": str(evidencias_por_nome[nome]),
            "STATUS": "CONFLITO_NOME_MULTIPLAS_COMPANHIAS",
        }
        for nome, tokens in sorted(empresas_por_nome.items())
        if len(tokens) > 1
    ]

    saida = []
    revisoes = []

    for linha in inventario:
        if linha.get("STATUS", "").strip().upper() != "SEM_EVIDENCIA_SUFICIENTE":
            saida.append(linha)
            continue

        chave = (int(linha["ANO"]), linha["TICKER"].strip().upper())
        nomes = nomes_por_ticker_ano.get(chave, ())

        candidatos: set[tuple[str, str]] = set()
        nomes_usados = []

        for nome in nomes:
            tokens = empresas_por_nome.get(nome, set())
            if len(tokens) == 1 and evidencias_por_nome[nome] >= 2:
                candidatos.update(tokens)
                nomes_usados.append(nome)

        if len(candidatos) == 0:
            saida.append(linha)
            continue

        if len(candidatos) > 1:
            revisoes.append(
                {
                    "ANO": str(linha["ANO"]),
                    "TICKER": linha["TICKER"],
                    "NOMES": "|".join(nomes_usados),
                    "CANDIDATOS": "|".join(
                        f"{tipo}:{cd}"
                        for tipo, cd in sorted(candidatos)
                    ),
                    "STATUS": "REVISAO_NOME_MULTIPLOS_CANDIDATOS",
                }
            )
            saida.append(linha)
            continue

        universo, cd = next(iter(candidatos))
        nova = dict(linha)

        if universo == "FORA":
            nova["STATUS"] = "FORA_UNIVERSO_NOME_B3"
            nova["CD_CVM"] = cd
        else:
            tipo = linha.get("TIPO_ATIVO", "").strip().upper()
            classe = linha.get("CLASSE", "").strip().upper()
            ids = instrumentos_por_chave.get(
                (cd, tipo, classe),
                set(),
            )

            if len(ids) == 1:
                nova["STATUS"] = "ALIAS_EXISTENTE_NOME_B3"
                nova["INSTRUMENTO_ID"] = next(iter(ids))
                nova["CD_CVM"] = cd
            elif len(ids) == 0:
                nova["STATUS"] = "NOVO_INSTRUMENTO_HISTORICO_NOME_B3"
                nova["CD_CVM"] = cd
                nova["CHAVE_INSTRUMENTO"] = f"{cd}|{tipo}|{classe}"
            else:
                revisoes.append(
                    {
                        "ANO": str(linha["ANO"]),
                        "TICKER": linha["TICKER"],
                        "NOMES": "|".join(nomes_usados),
                        "CANDIDATOS": "|".join(sorted(ids)),
                        "STATUS": "REVISAO_NOME_MULTIPLOS_IDS",
                    }
                )
                saida.append(linha)
                continue

        nova["FONTE"] = "COTAHIST_NOME_RESUMIDO_EXATO"
        nova["DETALHE"] = (
            "NOME_RESUMIDO B3 exato, com ao menos duas evidências fortes, "
            "aponta para uma única companhia histórica"
        )
        saida.append(nova)

    saida.sort(key=lambda x: (-int(x["ANO"]), x["TICKER"]))
    return saida, conflitos_nomes, revisoes

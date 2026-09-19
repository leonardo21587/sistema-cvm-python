from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from src.mercado.providers.cvm_fca import FcaValorMobiliario


_STOPWORDS = {
    "S", "A", "SA", "CIA", "COMPANHIA", "DE", "DA", "DO", "DAS", "DOS",
    "E", "EM", "PARA", "THE",
}


@dataclass(frozen=True)
class CandidatoNomeFca:
    cd_cvm: str
    nome_empresarial: str
    regra: str


def _normalizar(valor: object) -> str:
    texto = str(valor or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        ch for ch in texto
        if not unicodedata.combining(ch)
    )
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return " ".join(texto.split())


def _tokens(valor: object) -> tuple[str, ...]:
    return tuple(
        token
        for token in _normalizar(valor).split()
        if token not in _STOPWORDS and len(token) >= 3
    )


def _compacto(valor: object) -> str:
    return "".join(_tokens(valor))


def _token_b3_casa(token_b3: str, token_fca: str) -> bool:
    if token_b3 == token_fca:
        return True
    if len(token_b3) >= 5 and token_fca.startswith(token_b3):
        return True
    if len(token_fca) >= 5 and token_b3.startswith(token_fca):
        return True
    return False


def _regra_match(nome_b3: str, nome_fca: str) -> str | None:
    tb3 = _tokens(nome_b3)
    tfca = _tokens(nome_fca)
    if not tb3 or not tfca:
        return None

    cb3 = _compacto(nome_b3)
    cfca = _compacto(nome_fca)

    if cb3 == cfca and len(cb3) >= 5:
        return "COMPACTO_EXATO"

    if len(cb3) >= 6 and cfca.startswith(cb3):
        return "COMPACTO_PREFIXO"

    usados: set[int] = set()
    for token_b3 in tb3:
        achou = None
        for i, token_fca in enumerate(tfca):
            if i in usados:
                continue
            if _token_b3_casa(token_b3, token_fca):
                achou = i
                break
        if achou is None:
            return None
        usados.add(achou)

    if len(tb3) >= 2:
        return "TOKENS_PREFIXO"

    if len(tb3) == 1 and len(tb3[0]) >= 6:
        return "TOKEN_UNICO_FORTE"

    return None


def indexar_companhias_fca(
    registros: Iterable[FcaValorMobiliario],
) -> dict[str, set[str]]:
    nomes_por_cd: dict[str, set[str]] = defaultdict(set)

    for registro in registros:
        if not registro.cd_cvm:
            continue
        cd = registro.cd_cvm.zfill(6)
        nome = _normalizar(registro.nome_empresarial)
        if nome:
            nomes_por_cd[cd].add(nome)

    return nomes_por_cd


def candidatos_nome_fca(
    *,
    nome_b3: str,
    nomes_por_cd: dict[str, set[str]],
) -> list[CandidatoNomeFca]:
    por_cd: dict[str, CandidatoNomeFca] = {}

    for cd, nomes in nomes_por_cd.items():
        melhor: CandidatoNomeFca | None = None
        prioridade = {
            "COMPACTO_EXATO": 4,
            "COMPACTO_PREFIXO": 3,
            "TOKENS_PREFIXO": 2,
            "TOKEN_UNICO_FORTE": 1,
        }

        for nome in nomes:
            regra = _regra_match(nome_b3, nome)
            if regra is None:
                continue
            atual = CandidatoNomeFca(cd, nome, regra)
            if (
                melhor is None
                or prioridade[atual.regra] > prioridade[melhor.regra]
            ):
                melhor = atual

        if melhor is not None:
            por_cd[cd] = melhor

    return sorted(
        por_cd.values(),
        key=lambda x: (x.cd_cvm, x.nome_empresarial),
    )


def reconciliar_pendencias_por_nome_fca(
    *,
    inventario: Iterable[dict[str, str]],
    nomes_b3: dict[tuple[int, str], tuple[str, ...]],
    registros_fca: Iterable[FcaValorMobiliario],
    cd_cvm_sistema: set[str],
    instrumentos_por_chave: dict[tuple[str, str, str], set[str]],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    inventario = [dict(x) for x in inventario]
    nomes_por_cd = indexar_companhias_fca(registros_fca)

    candidatos_ticker: dict[str, list[dict[str, str]]] = defaultdict(list)

    for linha in inventario:
        if linha.get("STATUS", "") != "SEM_EVIDENCIA_SUFICIENTE":
            continue

        ano = int(linha["ANO"])
        ticker = linha["TICKER"].strip().upper()

        for nome_b3 in nomes_b3.get((ano, ticker), ()):
            candidatos = candidatos_nome_fca(
                nome_b3=nome_b3,
                nomes_por_cd=nomes_por_cd,
            )
            for cand in candidatos:
                candidatos_ticker[ticker].append(
                    {
                        "ANO": str(ano),
                        "TICKER": ticker,
                        "NOME_B3": nome_b3,
                        "CD_CVM": cand.cd_cvm,
                        "NOME_FCA": cand.nome_empresarial,
                        "REGRA": cand.regra,
                    }
                )

    decisao_por_ticker: dict[str, tuple[str, str]] = {}
    revisoes: list[dict[str, str]] = []

    for ticker, itens in sorted(candidatos_ticker.items()):
        cds = {x["CD_CVM"] for x in itens}
        if len(cds) != 1:
            if cds:
                revisoes.append(
                    {
                        "TICKER": ticker,
                        "CDS_CANDIDATOS": "|".join(sorted(cds)),
                        "STATUS": "REVISAO_NOME_FCA_MULTIPLOS_CD_CVM",
                    }
                )
            continue

        cd = next(iter(cds))
        regras = {x["REGRA"] for x in itens}
        anos = {x["ANO"] for x in itens}

        alta_confianca = bool(
            regras & {"COMPACTO_EXATO", "COMPACTO_PREFIXO"}
        ) or len(anos) >= 2

        if alta_confianca:
            decisao_por_ticker[ticker] = (
                cd,
                "|".join(sorted(regras)),
            )

    saida = []

    for linha in inventario:
        if linha.get("STATUS", "") != "SEM_EVIDENCIA_SUFICIENTE":
            saida.append(linha)
            continue

        ticker = linha["TICKER"].strip().upper()
        decisao = decisao_por_ticker.get(ticker)
        if decisao is None:
            saida.append(linha)
            continue

        cd, regras = decisao
        tipo = linha.get("TIPO_ATIVO", "").strip().upper()
        classe = linha.get("CLASSE", "").strip().upper()

        nova = dict(linha)

        if cd not in cd_cvm_sistema:
            nova["STATUS"] = "FORA_UNIVERSO_NOME_FCA"
            nova["CD_CVM"] = cd
        else:
            ids = instrumentos_por_chave.get(
                (cd, tipo, classe),
                set(),
            )
            if len(ids) == 1:
                nova["STATUS"] = "ALIAS_EXISTENTE_NOME_FCA"
                nova["INSTRUMENTO_ID"] = next(iter(ids))
                nova["CD_CVM"] = cd
            elif len(ids) == 0:
                nova["STATUS"] = "NOVO_INSTRUMENTO_HISTORICO_NOME_FCA"
                nova["CD_CVM"] = cd
                nova["CHAVE_INSTRUMENTO"] = f"{cd}|{tipo}|{classe}"
            else:
                revisoes.append(
                    {
                        "TICKER": ticker,
                        "CDS_CANDIDATOS": cd,
                        "STATUS": "REVISAO_NOME_FCA_MULTIPLOS_IDS",
                    }
                )
                saida.append(linha)
                continue

        nova["FONTE"] = "COTAHIST_NOME_B3_FCA_NOME_EMPRESARIAL"
        nova["DETALHE"] = (
            "NOME_RESUMIDO B3 corresponde de forma conservadora a um único "
            f"CD_CVM no FCA; regras={regras}"
        )
        saida.append(nova)

    saida.sort(key=lambda x: (-int(x["ANO"]), x["TICKER"]))

    candidatos_flat = [
        item
        for ticker in sorted(candidatos_ticker)
        for item in sorted(
            candidatos_ticker[ticker],
            key=lambda x: (
                int(x["ANO"]),
                x["CD_CVM"],
                x["NOME_B3"],
            ),
        )
    ]

    return saida, candidatos_flat, revisoes

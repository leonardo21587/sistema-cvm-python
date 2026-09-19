from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


STATUS_ID = {"RESOLVIDO_EXISTENTE", "ALIAS_EXISTENTE_FORTE"}
STATUS_NOVO = {"NOVO_INSTRUMENTO_HISTORICO_CANDIDATO"}
STATUS_FORA = {"FORA_UNIVERSO_SISTEMA"}
STATUS_PENDENTE = {"SEM_EVIDENCIA_SUFICIENTE"}


@dataclass(frozen=True)
class AncoraIsin:
    tipo_token: str
    valor_token: str
    tipo_ativo: str
    classe: str


def _isins(valor: str) -> tuple[str, ...]:
    return tuple(
        sorted({
            item.strip().upper()
            for item in str(valor or "").split("|")
            if item.strip()
        })
    )


def _ancora(linha: dict[str, str]) -> AncoraIsin | None:
    status = linha.get("STATUS", "").strip().upper()
    tipo = linha.get("TIPO_ATIVO", "").strip().upper()
    classe = linha.get("CLASSE", "").strip().upper()

    if status in STATUS_ID:
        instrumento_id = linha.get("INSTRUMENTO_ID", "").strip()
        if instrumento_id:
            return AncoraIsin("ID", instrumento_id, tipo, classe)

    if status in STATUS_NOVO:
        chave = linha.get("CHAVE_INSTRUMENTO", "").strip()
        if chave:
            return AncoraIsin("NOVO", chave, tipo, classe)

    if status in STATUS_FORA:
        cd = linha.get("CD_CVM", "").strip()
        if cd:
            return AncoraIsin("FORA", cd, tipo, classe)

    return None


def reconciliar_por_isin_global(
    *,
    inventario: Iterable[dict[str, str]],
    diagnosticos: Iterable[dict[str, str]],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """
    Usa somente ISINs ligados a uma única âncora forte já conhecida.

    Não faz propagação transitiva: linhas resolvidas nesta etapa não viram
    novas âncoras no mesmo processamento.
    """
    inventario = [dict(x) for x in inventario]
    diag_por_chave = {
        (str(x["ANO"]), x["TICKER"].strip().upper()): dict(x)
        for x in diagnosticos
    }

    ancoras_por_isin: dict[str, set[AncoraIsin]] = defaultdict(set)

    for linha in inventario:
        ancora = _ancora(linha)
        if ancora is None:
            continue

        diag = diag_por_chave.get(
            (str(linha["ANO"]), linha["TICKER"].strip().upper())
        )
        if diag is None:
            continue

        for isin in _isins(diag.get("ISINS", "")):
            ancoras_por_isin[isin].add(ancora)

    conflitos_isin = []
    for isin, ancoras in sorted(ancoras_por_isin.items()):
        identidades = {
            (a.tipo_token, a.valor_token, a.tipo_ativo, a.classe)
            for a in ancoras
        }
        if len(identidades) > 1:
            conflitos_isin.append(
                {
                    "ISIN": isin,
                    "ANCORAS": "|".join(
                        f"{a.tipo_token}:{a.valor_token}:{a.tipo_ativo}:{a.classe}"
                        for a in sorted(
                            ancoras,
                            key=lambda x: (
                                x.tipo_token,
                                x.valor_token,
                                x.tipo_ativo,
                                x.classe,
                            ),
                        )
                    ),
                    "STATUS": "CONFLITO_ISIN_MULTIPLAS_ANCORAS",
                }
            )

    saida = []
    revisoes = []

    for linha in inventario:
        status = linha.get("STATUS", "").strip().upper()
        if status not in STATUS_PENDENTE:
            saida.append(linha)
            continue

        diag = diag_por_chave.get(
            (str(linha["ANO"]), linha["TICKER"].strip().upper())
        )
        if diag is None:
            saida.append(linha)
            continue

        tipo_obs = linha.get("TIPO_ATIVO", "").strip().upper()
        classe_obs = linha.get("CLASSE", "").strip().upper()

        candidatas: set[AncoraIsin] = set()
        isins_usados = []

        for isin in _isins(diag.get("ISINS", "")):
            ancoras = ancoras_por_isin.get(isin, set())
            identidades = {
                a
                for a in ancoras
                if a.tipo_ativo == tipo_obs
                and a.classe == classe_obs
            }
            if len(identidades) == 1:
                candidatas.update(identidades)
                isins_usados.append(isin)

        if len(candidatas) == 0:
            saida.append(linha)
            continue

        if len(candidatas) > 1:
            revisoes.append(
                {
                    "ANO": str(linha["ANO"]),
                    "TICKER": linha["TICKER"],
                    "ISINS": "|".join(sorted(isins_usados)),
                    "CANDIDATOS": "|".join(
                        f"{a.tipo_token}:{a.valor_token}"
                        for a in sorted(
                            candidatas,
                            key=lambda x: (x.tipo_token, x.valor_token),
                        )
                    ),
                    "STATUS": "REVISAO_ISIN_MULTIPLOS_CANDIDATOS",
                }
            )
            saida.append(linha)
            continue

        ancora = next(iter(candidatas))
        nova = dict(linha)

        if ancora.tipo_token == "ID":
            nova["STATUS"] = "ALIAS_EXISTENTE_ISIN_GLOBAL"
            nova["INSTRUMENTO_ID"] = ancora.valor_token
        elif ancora.tipo_token == "NOVO":
            nova["STATUS"] = "NOVO_INSTRUMENTO_HISTORICO_ISIN_GLOBAL"
            nova["CHAVE_INSTRUMENTO"] = ancora.valor_token
            partes = ancora.valor_token.split("|")
            if len(partes) == 3:
                nova["CD_CVM"] = partes[0]
                nova["TIPO_ATIVO"] = partes[1]
                nova["CLASSE"] = partes[2]
        elif ancora.tipo_token == "FORA":
            nova["STATUS"] = "FORA_UNIVERSO_ISIN_GLOBAL"
            nova["CD_CVM"] = ancora.valor_token

        nova["FONTE"] = "ISIN_GLOBAL_ANCORA_UNICA"
        nova["DETALHE"] = (
            "ISIN histórico coincide com uma única identidade forte "
            "de tipo/classe compatíveis"
        )
        saida.append(nova)

    saida.sort(key=lambda x: (-int(x["ANO"]), x["TICKER"]))
    return saida, conflitos_isin, revisoes

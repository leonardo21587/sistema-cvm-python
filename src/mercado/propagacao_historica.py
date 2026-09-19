from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


STATUS_ANCORA_EXISTENTE = {
    "RESOLVIDO_EXISTENTE",
    "ALIAS_EXISTENTE_FORTE",
}
STATUS_ANCORA_NOVO = {
    "NOVO_INSTRUMENTO_HISTORICO_CANDIDATO",
}
STATUS_ANCORA_FORA = {
    "FORA_UNIVERSO_SISTEMA",
}
STATUS_PENDENTE = {
    "SEM_EVIDENCIA_SUFICIENTE",
}


@dataclass(frozen=True)
class SegmentoTicker:
    ticker: str
    anos: tuple[int, ...]
    linhas: tuple[dict[str, str], ...]


def _token_identidade(linha: dict[str, str]) -> tuple[str, str] | None:
    status = linha["STATUS"].strip().upper()

    if status in STATUS_ANCORA_EXISTENTE:
        instrumento_id = linha.get("INSTRUMENTO_ID", "").strip()
        if instrumento_id:
            return ("ID", instrumento_id)
        return None

    if status in STATUS_ANCORA_NOVO:
        chave = linha.get("CHAVE_INSTRUMENTO", "").strip()
        if chave:
            return ("NOVO", chave)
        return None

    if status in STATUS_ANCORA_FORA:
        cd_cvm = linha.get("CD_CVM", "").strip()
        if cd_cvm:
            return ("FORA", cd_cvm)
        return None

    return None


def segmentar_por_continuidade(
    linhas: Iterable[dict[str, str]],
) -> list[SegmentoTicker]:
    por_ticker: dict[str, list[dict[str, str]]] = defaultdict(list)
    for linha in linhas:
        por_ticker[linha["TICKER"].strip().upper()].append(dict(linha))

    segmentos: list[SegmentoTicker] = []

    for ticker, itens in sorted(por_ticker.items()):
        itens.sort(key=lambda x: int(x["ANO"]))
        atual: list[dict[str, str]] = []
        ultimo_ano: int | None = None

        for linha in itens:
            ano = int(linha["ANO"])
            if ultimo_ano is None or ano == ultimo_ano + 1:
                atual.append(linha)
            else:
                segmentos.append(
                    SegmentoTicker(
                        ticker=ticker,
                        anos=tuple(int(x["ANO"]) for x in atual),
                        linhas=tuple(atual),
                    )
                )
                atual = [linha]
            ultimo_ano = ano

        if atual:
            segmentos.append(
                SegmentoTicker(
                    ticker=ticker,
                    anos=tuple(int(x["ANO"]) for x in atual),
                    linhas=tuple(atual),
                )
            )

    return segmentos


def propagar_identidades(
    linhas: Iterable[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Propaga somente dentro de um trecho anual contínuo do mesmo ticker.

    Um segmento é propagável apenas quando possui exatamente uma identidade
    forte. Segmentos sem âncora permanecem pendentes. Segmentos com âncoras
    conflitantes viram revisão e não sofrem alteração.
    """
    saida: list[dict[str, str]] = []
    revisoes: list[dict[str, str]] = []

    for segmento in segmentar_por_continuidade(linhas):
        tokens = {
            token
            for linha in segmento.linhas
            if (token := _token_identidade(linha)) is not None
        }

        if len(tokens) > 1:
            revisoes.append(
                {
                    "TICKER": segmento.ticker,
                    "ANOS": "|".join(str(x) for x in segmento.anos),
                    "TOKENS": "|".join(
                        f"{tipo}:{valor}"
                        for tipo, valor in sorted(tokens)
                    ),
                    "STATUS": "REVISAO_MULTIPLAS_ANCORAS_NO_SEGMENTO",
                }
            )
            saida.extend(dict(x) for x in segmento.linhas)
            continue

        token = next(iter(tokens)) if len(tokens) == 1 else None

        for original in segmento.linhas:
            linha = dict(original)
            status = linha["STATUS"].strip().upper()

            if status not in STATUS_PENDENTE or token is None:
                saida.append(linha)
                continue

            tipo_token, valor_token = token

            if tipo_token == "ID":
                linha["STATUS"] = "ALIAS_EXISTENTE_PROPAGADO"
                linha["INSTRUMENTO_ID"] = valor_token
                linha["FONTE"] = (
                    "PROPAGACAO_TEMPORAL_SEGMENTO_CONTINUO"
                )
                linha["DETALHE"] = (
                    "identidade herdada de âncora forte do mesmo ticker "
                    "em sequência anual contínua"
                )

            elif tipo_token == "NOVO":
                partes = valor_token.split("|")
                linha["STATUS"] = (
                    "NOVO_INSTRUMENTO_HISTORICO_PROPAGADO"
                )
                linha["CHAVE_INSTRUMENTO"] = valor_token
                if len(partes) == 3:
                    linha["CD_CVM"] = partes[0]
                    linha["TIPO_ATIVO"] = partes[1]
                    linha["CLASSE"] = partes[2]
                linha["FONTE"] = (
                    "PROPAGACAO_TEMPORAL_SEGMENTO_CONTINUO"
                )
                linha["DETALHE"] = (
                    "grupo histórico herdado de âncora forte do mesmo "
                    "ticker em sequência anual contínua"
                )

            elif tipo_token == "FORA":
                linha["STATUS"] = "FORA_UNIVERSO_PROPAGADO"
                linha["CD_CVM"] = valor_token
                linha["FONTE"] = (
                    "PROPAGACAO_TEMPORAL_SEGMENTO_CONTINUO"
                )
                linha["DETALHE"] = (
                    "fora do universo herdado de âncora forte do mesmo "
                    "ticker em sequência anual contínua"
                )

            saida.append(linha)

    saida.sort(key=lambda x: (-int(x["ANO"]), x["TICKER"]))
    return saida, revisoes

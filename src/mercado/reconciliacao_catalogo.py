from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class EvidenciaVinculo:
    ticker: str
    cd_cvm: str | None
    status: str
    fonte: str
    prioridade: int


@dataclass(frozen=True)
class ResultadoVinculo:
    ticker: str
    cd_cvm: str | None
    status: str
    fontes: tuple[str, ...]
    conflito: str | None


def resolver_evidencias(
    ticker: str,
    evidencias: list[EvidenciaVinculo],
) -> ResultadoVinculo:
    """
    Consolida evidências independentes sem mascarar conflito de CD_CVM.

    Regras:
    - evidências vazias não resolvem o ticker;
    - dois CD_CVM diferentes bloqueiam promoção;
    - FORA_UNIVERSO_SISTEMA é aceito apenas se não houver evidência
      conflitante de vínculo a uma empresa do sistema;
    - prioridade só escolhe a descrição/status entre evidências coerentes;
      nunca vence um conflito factual.
    """
    ticker = str(ticker).strip().upper()
    validas = [
        item
        for item in evidencias
        if item.ticker.strip().upper() == ticker
    ]

    if not validas:
        return ResultadoVinculo(
            ticker=ticker,
            cd_cvm=None,
            status="NAO_RESOLVIDO",
            fontes=(),
            conflito=None,
        )

    codigos = {
        item.cd_cvm
        for item in validas
        if item.cd_cvm
    }
    fontes = tuple(sorted({item.fonte for item in validas if item.fonte}))

    if len(codigos) > 1:
        return ResultadoVinculo(
            ticker=ticker,
            cd_cvm=None,
            status="CONFLITO",
            fontes=fontes,
            conflito="CD_CVM_DIVERGENTE:" + "|".join(sorted(codigos)),
        )

    dentro = [
        item
        for item in validas
        if item.status not in {
            "FORA_UNIVERSO_SISTEMA",
            "NAO_RESOLVIDO",
            "REVISAO",
        }
        and item.cd_cvm
    ]
    fora = [
        item
        for item in validas
        if item.status == "FORA_UNIVERSO_SISTEMA"
    ]

    if dentro and fora:
        return ResultadoVinculo(
            ticker=ticker,
            cd_cvm=None,
            status="CONFLITO",
            fontes=fontes,
            conflito="DENTRO_E_FORA_UNIVERSO",
        )

    escolhido = max(validas, key=lambda item: item.prioridade)
    cd_cvm = next(iter(codigos)) if len(codigos) == 1 else None

    return ResultadoVinculo(
        ticker=ticker,
        cd_cvm=cd_cvm,
        status=escolhido.status,
        fontes=fontes,
        conflito=None,
    )


def sobrepoe(
    inicio_a: date,
    fim_a: date,
    inicio_b: date,
    fim_b: date,
) -> bool:
    return inicio_a <= fim_b and inicio_b <= fim_a

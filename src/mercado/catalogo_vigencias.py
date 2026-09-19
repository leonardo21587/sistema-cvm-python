from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


DATA_INICIO_ALVO = date(2010, 1, 1)
FIM_JANELA_2025 = date(2025, 12, 31)


@dataclass(frozen=True)
class EvidenciaFcaTicker:
    ano: int
    ticker: str
    cd_cvm: str
    data_referencia: date | None
    versao: int | None
    data_inicio_negociacao: date | None
    data_fim_negociacao: date | None
    data_inicio_listagem: date | None
    data_fim_listagem: date | None


@dataclass(frozen=True)
class ObservacaoIsin:
    data: date
    ticker: str
    isin: str


@dataclass(frozen=True)
class ResultadoCatalogoTemporal:
    instrumentos: list[dict[str, str]]
    tickers: list[dict[str, str]]
    identificadores: list[dict[str, str]]
    mapa_tickers_2025: list[dict[str, str]]
    revisao: list[dict[str, str]]
    gate_aprovado: bool


def _texto(valor: object) -> str:
    return str(valor or "").strip()


def _data(valor: object) -> date:
    texto = _texto(valor)
    if not texto:
        raise ValueError("Data obrigatoria ausente.")
    return date.fromisoformat(texto)


def _data_opcional(valor: object) -> date | None:
    texto = _texto(valor)
    if not texto:
        return None
    return date.fromisoformat(texto)


def _intervalo_contem(
    inicio: date,
    fim: date | None,
    alvo: date,
) -> bool:
    return inicio <= alvo and (fim is None or alvo < fim)


def _normalizar_linha_instrumento(linha: dict[str, str]) -> dict[str, str]:
    return {
        "INSTRUMENTO_ID": str(int(_texto(linha["INSTRUMENTO_ID"]))),
        "CD_CVM": _texto(linha["CD_CVM"]).zfill(6),
        "TIPO_ATIVO": _texto(linha["TIPO_ATIVO"]).upper(),
        "CLASSE": _texto(linha["CLASSE"]).upper(),
        "MOEDA": _texto(linha.get("MOEDA", "BRL")).upper() or "BRL",
        "DT_INICIO": _data(linha["DT_INICIO"]).isoformat(),
        "DT_FIM": (
            _data_opcional(linha.get("DT_FIM", "")).isoformat()
            if _data_opcional(linha.get("DT_FIM", ""))
            else ""
        ),
        "STATUS": _texto(linha["STATUS"]).upper(),
        "FONTE": _texto(linha["FONTE"]),
    }


def _normalizar_linha_ticker(linha: dict[str, str]) -> dict[str, str]:
    return {
        "INSTRUMENTO_ID": str(int(_texto(linha["INSTRUMENTO_ID"]))),
        "BOLSA": _texto(linha["BOLSA"]).upper(),
        "TICKER": _texto(linha["TICKER"]).upper(),
        "DT_INICIO": _data(linha["DT_INICIO"]).isoformat(),
        "DT_FIM": (
            _data_opcional(linha.get("DT_FIM", "")).isoformat()
            if _data_opcional(linha.get("DT_FIM", ""))
            else ""
        ),
        "STATUS": _texto(linha["STATUS"]).upper(),
        "FONTE": _texto(linha["FONTE"]),
    }


def _normalizar_linha_identificador(linha: dict[str, str]) -> dict[str, str]:
    return {
        "INSTRUMENTO_ID": str(int(_texto(linha["INSTRUMENTO_ID"]))),
        "TIPO_IDENTIFICADOR": _texto(
            linha["TIPO_IDENTIFICADOR"]
        ).upper(),
        "VALOR": _texto(linha["VALOR"]).upper(),
        "DT_INICIO": _data(linha["DT_INICIO"]).isoformat(),
        "DT_FIM": (
            _data_opcional(linha.get("DT_FIM", "")).isoformat()
            if _data_opcional(linha.get("DT_FIM", ""))
            else ""
        ),
        "FONTE": _texto(linha["FONTE"]),
    }


def _melhor_evidencia_fca(
    evidencias: list[EvidenciaFcaTicker],
    *,
    primeira_data_2025: date,
    ultima_data_2025: date,
) -> EvidenciaFcaTicker | None:
    candidatas = []

    for item in evidencias:
        inicio = (
            item.data_inicio_negociacao
            or item.data_inicio_listagem
        )
        fim = (
            item.data_fim_negociacao
            or item.data_fim_listagem
        )

        if inicio is not None and inicio > ultima_data_2025:
            continue
        if fim is not None and primeira_data_2025 >= fim:
            continue

        candidatas.append(item)

    if not candidatas:
        return None

    def ranking(item: EvidenciaFcaTicker):
        referencia = item.data_referencia or date(item.ano, 12, 31)
        versao = item.versao if item.versao is not None else -1
        return referencia, versao, item.ano

    return max(candidatas, key=ranking)


def _inicio_por_evidencia(
    *,
    linha_ticker: dict[str, str],
    evidencias: list[EvidenciaFcaTicker],
) -> tuple[date, str]:
    inicio_validado = _data_opcional(
        linha_ticker.get("DT_INICIO_VALIDADA", "")
    )
    if inicio_validado is not None:
        return max(DATA_INICIO_ALVO, inicio_validado), "EXCECAO_VALIDADA"

    primeira = _data(linha_ticker["PRIMEIRA_DATA_2025"])
    ultima = _data(linha_ticker["ULTIMA_DATA_2025"])
    melhor = _melhor_evidencia_fca(
        evidencias,
        primeira_data_2025=primeira,
        ultima_data_2025=ultima,
    )

    if melhor is not None:
        inicio = (
            melhor.data_inicio_negociacao
            or melhor.data_inicio_listagem
        )
        if inicio is not None:
            return max(DATA_INICIO_ALVO, inicio), "FCA_DATA_INICIO"

    anos = sorted({
        item.ano
        for item in evidencias
        if item.ano <= 2025
    })
    if anos and anos[0] < 2025:
        return max(DATA_INICIO_ALVO, date(anos[0], 1, 1)), "FCA_ANO_EVIDENCIA"

    return primeira, "COTAHIST_2025_PRIMEIRA_OBSERVACAO"


def _fim_por_evidencia(
    *,
    linha_ticker: dict[str, str],
    evidencias: list[EvidenciaFcaTicker],
) -> tuple[date | None, str]:
    fim_validado = _data_opcional(
        linha_ticker.get("DT_FIM_VALIDADA", "")
    )
    if fim_validado is not None:
        return fim_validado, "EXCECAO_VALIDADA"

    primeira = _data(linha_ticker["PRIMEIRA_DATA_2025"])
    ultima = _data(linha_ticker["ULTIMA_DATA_2025"])
    melhor = _melhor_evidencia_fca(
        evidencias,
        primeira_data_2025=primeira,
        ultima_data_2025=ultima,
    )

    if melhor is None:
        return None, ""

    fim = (
        melhor.data_fim_negociacao
        or melhor.data_fim_listagem
    )

    # O gate atual fecha somente fatos observáveis até o encerramento de 2025.
    # Eventos iniciados em 2026 serão tratados na atualização incremental.
    if fim is not None and fim <= FIM_JANELA_2025:
        return fim, "FCA_DATA_FIM"

    return None, ""


def _linha_existente_cobre_2025(
    linha: dict[str, str],
    *,
    primeira: date,
    ultima: date,
) -> bool:
    inicio = _data(linha["DT_INICIO"])
    fim = _data_opcional(linha.get("DT_FIM", ""))
    return (
        _intervalo_contem(inicio, fim, primeira)
        and _intervalo_contem(inicio, fim, ultima)
    )


def _resolver_em_tickers(
    tickers: list[dict[str, str]],
    *,
    ticker: str,
    data_referencia: date,
    bolsa: str = "B3",
) -> list[int]:
    ids = set()
    for linha in tickers:
        if linha["BOLSA"] != bolsa:
            continue
        if linha["TICKER"] != ticker:
            continue
        inicio = _data(linha["DT_INICIO"])
        fim = _data_opcional(linha.get("DT_FIM", ""))
        if _intervalo_contem(inicio, fim, data_referencia):
            ids.add(int(linha["INSTRUMENTO_ID"]))
    return sorted(ids)


def _ordenar_tickers(linhas: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        linhas,
        key=lambda x: (
            int(x["INSTRUMENTO_ID"]),
            x["BOLSA"],
            _data(x["DT_INICIO"]),
            x["TICKER"],
        ),
    )


def _ordenar_identificadores(
    linhas: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    return sorted(
        linhas,
        key=lambda x: (
            int(x["INSTRUMENTO_ID"]),
            x["TIPO_IDENTIFICADOR"],
            _data(x["DT_INICIO"]),
            x["VALOR"],
        ),
    )


def construir_catalogo_temporal(
    *,
    instrumentos_existentes: Iterable[dict[str, str]],
    instrumentos_candidatos: Iterable[dict[str, str]],
    tickers_existentes: Iterable[dict[str, str]],
    identificadores_existentes: Iterable[dict[str, str]],
    alocacoes: Iterable[dict[str, str]],
    tickers_reconciliados_2025: Iterable[dict[str, str]],
    evidencias_fca: Iterable[EvidenciaFcaTicker],
    observacoes_isin: Iterable[ObservacaoIsin],
) -> ResultadoCatalogoTemporal:
    instrumentos_base = [
        _normalizar_linha_instrumento(x)
        for x in instrumentos_existentes
    ]
    instrumentos = [
        _normalizar_linha_instrumento(x)
        for x in instrumentos_candidatos
    ]
    tickers = [
        _normalizar_linha_ticker(x)
        for x in tickers_existentes
    ]
    identificadores = [
        _normalizar_linha_identificador(x)
        for x in identificadores_existentes
    ]
    revisao: list[dict[str, str]] = []

    ids_base = {
        int(x["INSTRUMENTO_ID"]): x
        for x in instrumentos_base
    }
    ids_candidatos = {
        int(x["INSTRUMENTO_ID"]): x
        for x in instrumentos
    }

    for instrumento_id, original in ids_base.items():
        if ids_candidatos.get(instrumento_id) != original:
            revisao.append(
                {
                    "NIVEL": "INSTRUMENTO",
                    "CHAVE": str(instrumento_id),
                    "DETALHE": "INSTRUMENTO_EXISTENTE_NAO_PRESERVADO",
                }
            )

    alocacao_por_chave = {
        _texto(x["CHAVE_CANDIDATO"]): int(x["INSTRUMENTO_ID"])
        for x in alocacoes
    }

    fca_por_ticker_cd: dict[
        tuple[str, str],
        list[EvidenciaFcaTicker],
    ] = {}
    for item in evidencias_fca:
        chave = (item.ticker.upper(), item.cd_cvm.zfill(6))
        fca_por_ticker_cd.setdefault(chave, []).append(item)

    reconciliados = []
    for bruto in tickers_reconciliados_2025:
        if _texto(bruto.get("PROBLEMAS", "")):
            continue
        if _texto(bruto.get("STATUS_FINAL", "")).upper() == (
            "FORA_UNIVERSO_SISTEMA"
        ):
            continue

        ticker = _texto(bruto["TICKER"]).upper()
        cd_cvm = _texto(bruto["CD_CVM"]).zfill(6)
        tipo = _texto(bruto["TIPO_ATIVO"]).upper()
        classe = _texto(bruto["CLASSE"]).upper()
        chave = f"{cd_cvm}|{tipo}|{classe}"

        instrumento_id = alocacao_por_chave.get(chave)
        if instrumento_id is None:
            revisao.append(
                {
                    "NIVEL": "TICKER",
                    "CHAVE": ticker,
                    "DETALHE": f"SEM_ALOCACAO:{chave}",
                }
            )
            continue

        linha = dict(bruto)
        linha["_INSTRUMENTO_ID"] = str(instrumento_id)
        reconciliados.append(linha)

    mapa_tickers_2025: list[dict[str, str]] = []
    novas_linhas_por_ticker: dict[
        tuple[int, str],
        dict[str, str],
    ] = {}

    for linha in reconciliados:
        ticker = _texto(linha["TICKER"]).upper()
        cd_cvm = _texto(linha["CD_CVM"]).zfill(6)
        instrumento_id = int(linha["_INSTRUMENTO_ID"])
        primeira = _data(linha["PRIMEIRA_DATA_2025"])
        ultima = _data(linha["ULTIMA_DATA_2025"])

        existentes_mesmo_id = [
            x
            for x in tickers
            if int(x["INSTRUMENTO_ID"]) == instrumento_id
            and x["BOLSA"] == "B3"
            and x["TICKER"] == ticker
        ]
        cobertura = [
            x
            for x in existentes_mesmo_id
            if _linha_existente_cobre_2025(
                x,
                primeira=primeira,
                ultima=ultima,
            )
        ]

        if len(cobertura) > 1:
            revisao.append(
                {
                    "NIVEL": "TICKER",
                    "CHAVE": ticker,
                    "DETALHE": (
                        f"MULTIPLAS_VIGENCIAS_EXISTENTES_COBREM_2025:"
                        f"{instrumento_id}"
                    ),
                }
            )
            continue

        if len(cobertura) == 1:
            escolhida = cobertura[0]
            mapa_tickers_2025.append(
                {
                    "TICKER": ticker,
                    "INSTRUMENTO_ID": str(instrumento_id),
                    "ORIGEM_VIGENCIA": "PRESERVADA",
                    "DT_INICIO": escolhida["DT_INICIO"],
                    "DT_FIM": escolhida["DT_FIM"],
                    "PRIMEIRA_DATA_2025": primeira.isoformat(),
                    "ULTIMA_DATA_2025": ultima.isoformat(),
                }
            )
            continue

        evidencias = fca_por_ticker_cd.get((ticker, cd_cvm), [])
        inicio, fonte_inicio = _inicio_por_evidencia(
            linha_ticker=linha,
            evidencias=evidencias,
        )
        fim, fonte_fim = _fim_por_evidencia(
            linha_ticker=linha,
            evidencias=evidencias,
        )

        if inicio > primeira:
            revisao.append(
                {
                    "NIVEL": "TICKER",
                    "CHAVE": ticker,
                    "DETALHE": (
                        f"INICIO_APOS_PRIMEIRA_OBSERVACAO:"
                        f"{inicio}>{primeira}"
                    ),
                }
            )
            continue

        if fim is not None and not ultima < fim:
            revisao.append(
                {
                    "NIVEL": "TICKER",
                    "CHAVE": ticker,
                    "DETALHE": (
                        f"FIM_NAO_COBRE_ULTIMA_OBSERVACAO:"
                        f"{fim}<={ultima}"
                    ),
                }
            )
            continue

        fontes = [
            "B3_COTAHIST_2025",
            fonte_inicio,
            fonte_fim,
        ]
        fonte = "|".join(x for x in fontes if x)

        nova = {
            "INSTRUMENTO_ID": str(instrumento_id),
            "BOLSA": "B3",
            "TICKER": ticker,
            "DT_INICIO": inicio.isoformat(),
            "DT_FIM": fim.isoformat() if fim else "",
            "STATUS": "ENCERRADO" if fim else "VIGENTE",
            "FONTE": fonte,
        }
        tickers.append(nova)
        novas_linhas_por_ticker[(instrumento_id, ticker)] = nova

        mapa_tickers_2025.append(
            {
                "TICKER": ticker,
                "INSTRUMENTO_ID": str(instrumento_id),
                "ORIGEM_VIGENCIA": fonte_inicio,
                "DT_INICIO": nova["DT_INICIO"],
                "DT_FIM": nova["DT_FIM"],
                "PRIMEIRA_DATA_2025": primeira.isoformat(),
                "ULTIMA_DATA_2025": ultima.isoformat(),
            }
        )

    # Para continuidades observadas dentro do mesmo instrumento em 2025,
    # o inicio do ticker sucessor define o fim exclusivo do ticker anterior.
    por_instrumento: dict[int, list[dict[str, str]]] = {}
    for linha in reconciliados:
        por_instrumento.setdefault(
            int(linha["_INSTRUMENTO_ID"]),
            [],
        ).append(linha)

    for instrumento_id, itens in por_instrumento.items():
        if len(itens) <= 1:
            continue

        itens = sorted(
            itens,
            key=lambda x: (
                _data(x["PRIMEIRA_DATA_2025"]),
                _texto(x["TICKER"]).upper(),
            ),
        )

        for atual, proximo in zip(itens, itens[1:]):
            ticker_atual = _texto(atual["TICKER"]).upper()
            ticker_proximo = _texto(proximo["TICKER"]).upper()
            inicio_proximo = _data(proximo["PRIMEIRA_DATA_2025"])
            inicio_validado_proximo = _data_opcional(
                proximo.get("DT_INICIO_VALIDADA", "")
            )
            if inicio_validado_proximo is not None:
                inicio_proximo = inicio_validado_proximo

            nova_atual = novas_linhas_por_ticker.get(
                (instrumento_id, ticker_atual)
            )
            if nova_atual is None:
                # Linhas históricas já validadas não são reescritas.
                linhas_atuais = [
                    x
                    for x in tickers
                    if int(x["INSTRUMENTO_ID"]) == instrumento_id
                    and x["BOLSA"] == "B3"
                    and x["TICKER"] == ticker_atual
                    and _linha_existente_cobre_2025(
                        x,
                        primeira=_data(atual["PRIMEIRA_DATA_2025"]),
                        ultima=_data(atual["ULTIMA_DATA_2025"]),
                    )
                ]
                if len(linhas_atuais) == 1:
                    fim_existente = _data_opcional(
                        linhas_atuais[0].get("DT_FIM", "")
                    )
                    if fim_existente != inicio_proximo:
                        revisao.append(
                            {
                                "NIVEL": "CONTINUIDADE",
                                "CHAVE": (
                                    f"{ticker_atual}->{ticker_proximo}"
                                ),
                                "DETALHE": (
                                    "FIM_EXISTENTE_DIVERGE_SUCESSOR:"
                                    f"{fim_existente}!={inicio_proximo}"
                                ),
                            }
                        )
                continue

            fim_validado = _data_opcional(
                atual.get("DT_FIM_VALIDADA", "")
            )
            fim_atual = _data_opcional(nova_atual.get("DT_FIM", ""))

            if fim_validado is not None and fim_validado != inicio_proximo:
                revisao.append(
                    {
                        "NIVEL": "CONTINUIDADE",
                        "CHAVE": f"{ticker_atual}->{ticker_proximo}",
                        "DETALHE": (
                            "FIM_VALIDADO_DIVERGE_SUCESSOR:"
                            f"{fim_validado}!={inicio_proximo}"
                        ),
                    }
                )
                continue

            if fim_atual is not None and fim_atual != inicio_proximo:
                revisao.append(
                    {
                        "NIVEL": "CONTINUIDADE",
                        "CHAVE": f"{ticker_atual}->{ticker_proximo}",
                        "DETALHE": (
                            "FIM_FCA_DIVERGE_SUCESSOR:"
                            f"{fim_atual}!={inicio_proximo}"
                        ),
                    }
                )
                continue

            nova_atual["DT_FIM"] = inicio_proximo.isoformat()
            nova_atual["STATUS"] = "ENCERRADO"
            if "CONTINUIDADE_2025" not in nova_atual["FONTE"]:
                nova_atual["FONTE"] += "|CONTINUIDADE_2025"

    tickers = _ordenar_tickers(tickers)

    # Valida resolução das duas extremidades observadas de cada ticker 2025.
    for linha in reconciliados:
        ticker = _texto(linha["TICKER"]).upper()
        esperado = int(linha["_INSTRUMENTO_ID"])
        for campo in ("PRIMEIRA_DATA_2025", "ULTIMA_DATA_2025"):
            data_ref = _data(linha[campo])
            ids = _resolver_em_tickers(
                tickers,
                ticker=ticker,
                data_referencia=data_ref,
            )
            if ids != [esperado]:
                revisao.append(
                    {
                        "NIVEL": "RESOLUCAO",
                        "CHAVE": f"{ticker}|{data_ref}",
                        "DETALHE": (
                            f"ESPERADO={esperado};RESOLVIDOS="
                            + "|".join(str(x) for x in ids)
                        ),
                    }
                )

    # Ajusta apenas os instrumentos NOVOS. IDs piloto existentes ficam imutáveis.
    tickers_por_id: dict[int, list[dict[str, str]]] = {}
    for linha in tickers:
        tickers_por_id.setdefault(
            int(linha["INSTRUMENTO_ID"]),
            [],
        ).append(linha)

    instrumentos_ajustados = []
    for instrumento in instrumentos:
        instrumento_id = int(instrumento["INSTRUMENTO_ID"])
        if instrumento_id in ids_base:
            instrumentos_ajustados.append(instrumento)
            continue

        linhas = tickers_por_id.get(instrumento_id, [])
        if not linhas:
            revisao.append(
                {
                    "NIVEL": "INSTRUMENTO",
                    "CHAVE": str(instrumento_id),
                    "DETALHE": "NOVO_INSTRUMENTO_SEM_TICKER",
                }
            )
            instrumentos_ajustados.append(instrumento)
            continue

        inicio = min(_data(x["DT_INICIO"]) for x in linhas)
        finais = [
            _data_opcional(x.get("DT_FIM", ""))
            for x in linhas
        ]
        abertos = [
            x for x in linhas
            if _data_opcional(x.get("DT_FIM", "")) is None
        ]

        if abertos:
            fim_instrumento = None
            status = "ATIVO"
        else:
            fim_instrumento = max(x for x in finais if x is not None)
            status = "ENCERRADO"

        novo = dict(instrumento)
        novo["DT_INICIO"] = inicio.isoformat()
        novo["DT_FIM"] = (
            fim_instrumento.isoformat()
            if fim_instrumento is not None
            else ""
        )
        novo["STATUS"] = status
        if "VIGENCIAS_D4_2025" not in novo["FONTE"]:
            novo["FONTE"] = (
                novo["FONTE"] + "|VIGENCIAS_D4_2025"
            )
        instrumentos_ajustados.append(novo)

    instrumentos = sorted(
        instrumentos_ajustados,
        key=lambda x: int(x["INSTRUMENTO_ID"]),
    )

    # ISIN: somente evidência observada nos COTAHIST já liberados (2024/2025).
    observacoes_por_id_isin: dict[
        tuple[int, str],
        list[date],
    ] = {}
    for obs in observacoes_isin:
        ticker = obs.ticker.upper()
        isin = obs.isin.upper()
        ids = _resolver_em_tickers(
            tickers,
            ticker=ticker,
            data_referencia=obs.data,
        )
        if len(ids) != 1:
            revisao.append(
                {
                    "NIVEL": "ISIN",
                    "CHAVE": f"{ticker}|{obs.data}|{isin}",
                    "DETALHE": (
                        "TICKER_NAO_RESOLVE_UNIVOCAMENTE:"
                        + "|".join(str(x) for x in ids)
                    ),
                }
            )
            continue
        observacoes_por_id_isin.setdefault(
            (ids[0], isin),
            [],
        ).append(obs.data)

    por_id_novos_isins: dict[int, list[tuple[str, date, date]]] = {}
    for (instrumento_id, isin), datas in observacoes_por_id_isin.items():
        ordenadas = sorted(set(datas))
        por_id_novos_isins.setdefault(
            instrumento_id,
            [],
        ).append((isin, ordenadas[0], ordenadas[-1]))

    for instrumento_id, itens in sorted(por_id_novos_isins.items()):
        itens = sorted(itens, key=lambda x: (x[1], x[0]))

        for indice, (isin, primeira, ultima) in enumerate(itens):
            existentes = [
                x
                for x in identificadores
                if int(x["INSTRUMENTO_ID"]) == instrumento_id
                and x["TIPO_IDENTIFICADOR"] == "ISIN"
                and x["VALOR"] == isin
                and _intervalo_contem(
                    _data(x["DT_INICIO"]),
                    _data_opcional(x.get("DT_FIM", "")),
                    primeira,
                )
                and _intervalo_contem(
                    _data(x["DT_INICIO"]),
                    _data_opcional(x.get("DT_FIM", "")),
                    ultima,
                )
            ]
            if existentes:
                continue

            proximo_inicio = (
                itens[indice + 1][1]
                if indice + 1 < len(itens)
                else None
            )

            identificadores.append(
                {
                    "INSTRUMENTO_ID": str(instrumento_id),
                    "TIPO_IDENTIFICADOR": "ISIN",
                    "VALOR": isin,
                    "DT_INICIO": primeira.isoformat(),
                    "DT_FIM": (
                        proximo_inicio.isoformat()
                        if proximo_inicio is not None
                        else ""
                    ),
                    "FONTE": "B3_COTAHIST_2024_2025",
                }
            )

    identificadores = _ordenar_identificadores(identificadores)

    # Não permite dois ISINs diferentes simultâneos no mesmo instrumento.
    por_id_isin = {}
    for linha in identificadores:
        if linha["TIPO_IDENTIFICADOR"] != "ISIN":
            continue
        por_id_isin.setdefault(
            int(linha["INSTRUMENTO_ID"]),
            [],
        ).append(linha)

    for instrumento_id, linhas in por_id_isin.items():
        for i, atual in enumerate(linhas):
            inicio_a = _data(atual["DT_INICIO"])
            fim_a = _data_opcional(atual.get("DT_FIM", ""))
            for proximo in linhas[i + 1:]:
                if atual["VALOR"] == proximo["VALOR"]:
                    continue
                inicio_b = _data(proximo["DT_INICIO"])
                fim_b = _data_opcional(proximo.get("DT_FIM", ""))

                sobrepoe = (
                    inicio_a < (fim_b or date.max)
                    and inicio_b < (fim_a or date.max)
                )
                if sobrepoe:
                    revisao.append(
                        {
                            "NIVEL": "ISIN",
                            "CHAVE": str(instrumento_id),
                            "DETALHE": (
                                "ISINS_DIFERENTES_SOBREPOSTOS:"
                                f"{atual['VALOR']}~{proximo['VALOR']}"
                            ),
                        }
                    )

    gate_aprovado = len(revisao) == 0

    return ResultadoCatalogoTemporal(
        instrumentos=instrumentos,
        tickers=tickers,
        identificadores=identificadores,
        mapa_tickers_2025=sorted(
            mapa_tickers_2025,
            key=lambda x: x["TICKER"],
        ),
        revisao=revisao,
        gate_aprovado=gate_aprovado,
    )

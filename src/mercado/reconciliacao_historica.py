from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import csv

from src.mercado.classificacao import inferir_tipo_classe
from src.mercado.providers.cvm_fca import FcaValorMobiliario


@dataclass(frozen=True)
class ResultadoReconciliacaoHistorica:
    ticker: str
    status: str
    cd_cvm: str
    tipo_ativo: str
    classe: str
    instrumento_id: str
    chave_instrumento: str
    fonte: str
    detalhe: str


def ler_csv_semicolon(caminho: str | Path) -> list[dict[str, str]]:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def escrever_csv_semicolon(
    caminho: str | Path,
    linhas: list[dict[str, str]],
) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not linhas:
        caminho.write_text("", encoding="utf-8")
        return
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=list(linhas[0]),
            delimiter=";",
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def _indice_catalogo(
    instrumentos: Iterable[dict[str, str]],
) -> tuple[
    dict[tuple[str, str, str], set[int]],
    dict[str, set[int]],
]:
    por_chave: dict[tuple[str, str, str], set[int]] = {}
    por_cd: dict[str, set[int]] = {}

    for linha in instrumentos:
        instrumento_id = int(linha["INSTRUMENTO_ID"])
        cd = linha["CD_CVM"].strip().zfill(6)
        tipo = linha["TIPO_ATIVO"].strip().upper()
        classe = linha["CLASSE"].strip().upper()
        por_chave.setdefault((cd, tipo, classe), set()).add(instrumento_id)
        por_cd.setdefault(cd, set()).add(instrumento_id)

    return por_chave, por_cd


def _fca_por_ticker(
    registros_por_ano: dict[int, list[FcaValorMobiliario]],
) -> dict[str, list[tuple[int, FcaValorMobiliario]]]:
    indice: dict[str, list[tuple[int, FcaValorMobiliario]]] = {}
    for ano, registros in registros_por_ano.items():
        for registro in registros:
            ticker = registro.codigo_negociacao.strip().upper()
            if not ticker:
                continue
            indice.setdefault(ticker, []).append((ano, registro))
    return indice


def reconciliar_diagnostico(
    *,
    diagnostico: Iterable[dict[str, str]],
    instrumentos: Iterable[dict[str, str]],
    registros_fca_por_ano: dict[int, list[FcaValorMobiliario]],
    cd_cvm_sistema: set[str],
    excecoes_validadas: Iterable[dict[str, str]] = (),
    cnpj_sistema_para_cd_cvm: dict[str, str] | None = None,
) -> list[ResultadoReconciliacaoHistorica]:
    """
    Segunda passada conservadora para um ano histórico.

    Não cria IDs e não altera catálogo. Apenas separa:
    - alias para instrumento existente com evidência forte;
    - novo instrumento histórico por chave econômica;
    - fora do universo;
    - revisão manual/sem evidência.
    """
    instrumentos = list(instrumentos)
    por_chave, por_cd = _indice_catalogo(instrumentos)
    fca = _fca_por_ticker(registros_fca_por_ano)
    cnpj_sistema_para_cd_cvm = cnpj_sistema_para_cd_cvm or {}
    excecao_por_ticker = {
        linha.get("TICKER", "").strip().upper(): linha
        for linha in excecoes_validadas
        if linha.get("TICKER", "").strip()
    }

    saida: list[ResultadoReconciliacaoHistorica] = []

    for linha in diagnostico:
        ticker = linha["TICKER"].strip().upper()
        status_diag = linha["STATUS"].strip().upper()
        tipo_obs = linha.get("TIPO_ATIVO", "").strip().upper()
        classe_obs = linha.get("CLASSE", "").strip().upper()
        especificacoes = linha.get("ESPECIFICACOES", "")
        id_diag = linha.get("CANDIDATO_INSTRUMENTO_ID", "").strip()

        excecao = excecao_por_ticker.get(ticker)
        if excecao is not None:
            status_excecao = excecao.get("STATUS", "").strip().upper()
            cd_excecao = excecao.get("CD_CVM", "").strip().zfill(6)
            tipo_excecao = excecao.get("TIPO_ATIVO", "").strip().upper()
            classe_excecao = excecao.get("CLASSE", "").strip().upper()
            fonte_excecao = excecao.get("FONTE", "").strip() or "EXCECAO_VALIDADA"

            if status_excecao == "FORA_UNIVERSO_SISTEMA":
                saida.append(
                    ResultadoReconciliacaoHistorica(
                        ticker=ticker,
                        status="FORA_UNIVERSO_SISTEMA",
                        cd_cvm=cd_excecao,
                        tipo_ativo=tipo_excecao or tipo_obs,
                        classe=classe_excecao or classe_obs,
                        instrumento_id="",
                        chave_instrumento="",
                        fonte=fonte_excecao,
                        detalhe="exceção documental já validada",
                    )
                )
                continue

            if status_excecao == "RESOLVIDO_EXCECAO_VALIDADA":
                chave_exc = (
                    cd_excecao,
                    tipo_excecao or tipo_obs,
                    classe_excecao or classe_obs,
                )
                ids_exc = por_chave.get(chave_exc, set())

                if len(ids_exc) == 1:
                    saida.append(
                        ResultadoReconciliacaoHistorica(
                            ticker=ticker,
                            status="ALIAS_EXISTENTE_FORTE",
                            cd_cvm=cd_excecao,
                            tipo_ativo=chave_exc[1],
                            classe=chave_exc[2],
                            instrumento_id=str(next(iter(ids_exc))),
                            chave_instrumento="",
                            fonte=fonte_excecao,
                            detalhe="exceção documental já validada",
                        )
                    )
                    continue

                if len(ids_exc) > 1:
                    saida.append(
                        ResultadoReconciliacaoHistorica(
                            ticker=ticker,
                            status="REVISAO_EXCECAO_MULTIPLOS_IDS",
                            cd_cvm=cd_excecao,
                            tipo_ativo=chave_exc[1],
                            classe=chave_exc[2],
                            instrumento_id="",
                            chave_instrumento="",
                            fonte=fonte_excecao,
                            detalhe="ids=" + "|".join(
                                str(x) for x in sorted(ids_exc)
                            ),
                        )
                    )
                    continue

        if status_diag == "RESOLVIDO_CATALOGO":
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="RESOLVIDO_EXISTENTE",
                    cd_cvm="",
                    tipo_ativo=tipo_obs,
                    classe=classe_obs,
                    instrumento_id=id_diag or linha.get("ID_RUNTIME_INICIO", "").strip(),
                    chave_instrumento="",
                    fonte="CATALOGO_TEMPORAL",
                    detalhe="",
                )
            )
            continue

        if status_diag == "FORA_UNIVERSO_SISTEMA_FCA":
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="FORA_UNIVERSO_SISTEMA",
                    cd_cvm=linha.get("CD_CVM_FCA", "").strip(),
                    tipo_ativo=tipo_obs,
                    classe=classe_obs,
                    instrumento_id="",
                    chave_instrumento="",
                    fonte="FCA_ANO",
                    detalhe="",
                )
            )
            continue

        if status_diag == "CANDIDATO_ALIAS_ISIN" and id_diag:
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="ALIAS_EXISTENTE_FORTE",
                    cd_cvm="",
                    tipo_ativo=tipo_obs,
                    classe=classe_obs,
                    instrumento_id=id_diag,
                    chave_instrumento="",
                    fonte="ISIN_EXATO_CATALOGO",
                    detalhe="",
                )
            )
            continue

        if status_diag == "CANDIDATO_FCA_ID_CLASSE" and id_diag:
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="ALIAS_EXISTENTE_FORTE",
                    cd_cvm=linha.get("CD_CVM_CANDIDATO", "").strip(),
                    tipo_ativo=tipo_obs,
                    classe=classe_obs,
                    instrumento_id=id_diag,
                    chave_instrumento="",
                    fonte="FCA_CD_CVM+TIPO+CLASSE",
                    detalhe="",
                )
            )
            continue

        # Para casos fracos/sem evidência, usa FCA adjacente 2022–2024.
        itens = fca.get(ticker, [])
        cds_candidatos: set[str] = set()

        for _, registro in itens:
            if registro.cd_cvm:
                cd = registro.cd_cvm.zfill(6)
                if cd in cd_cvm_sistema:
                    cds_candidatos.add(cd)

            cnpj = "".join(
                ch for ch in str(registro.cnpj or "")
                if ch.isdigit()
            ).zfill(14)
            cd_por_cnpj = cnpj_sistema_para_cd_cvm.get(cnpj)
            if cd_por_cnpj:
                cds_candidatos.add(cd_por_cnpj.zfill(6))

        cds = sorted(cds_candidatos)

        if len(cds) > 1:
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="REVISAO_FCA_MULTIPLO_CD_CVM",
                    cd_cvm="|".join(cds),
                    tipo_ativo=tipo_obs,
                    classe=classe_obs,
                    instrumento_id="",
                    chave_instrumento="",
                    fonte="FCA_2022_2024",
                    detalhe="ticker associado a múltiplos CD_CVM na janela adjacente",
                )
            )
            continue

        cd = cds[0] if len(cds) == 1 else linha.get(
            "CD_CVM_CANDIDATO", ""
        ).strip()

        if not cd:
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="SEM_EVIDENCIA_SUFICIENTE",
                    cd_cvm="",
                    tipo_ativo=tipo_obs,
                    classe=classe_obs,
                    instrumento_id="",
                    chave_instrumento="",
                    fonte="",
                    detalhe="sem CD_CVM único no FCA 2022–2024",
                )
            )
            continue

        # Refina classe com FCA + especificação B3. Conflitos entre snapshots
        # adjacentes são mantidos para revisão, nunca resolvidos por maioria.
        classes: set[tuple[str, str]] = set()
        for _, registro in itens:
            if not registro.cd_cvm or registro.cd_cvm.zfill(6) != cd:
                continue
            tipo, classe = inferir_tipo_classe(
                ticker=ticker,
                valor_mobiliario=registro.valor_mobiliario,
                sigla_classe_preferencial=registro.sigla_classe_preferencial,
                classe_preferencial=registro.classe_preferencial,
                composicao_unit=registro.composicao_bdr_unit,
                especificacoes_cotahist=especificacoes,
            )
            if tipo and classe:
                classes.add((tipo, classe))

        if not classes and tipo_obs and classe_obs:
            classes.add((tipo_obs, classe_obs))

        if len(classes) != 1:
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="REVISAO_CLASSE",
                    cd_cvm=cd,
                    tipo_ativo=tipo_obs,
                    classe=classe_obs,
                    instrumento_id="",
                    chave_instrumento="",
                    fonte="FCA_2022_2024+COTAHIST",
                    detalhe=(
                        "classes inferidas="
                        + "|".join(
                            f"{tipo}/{classe}"
                            for tipo, classe in sorted(classes)
                        )
                    ),
                )
            )
            continue

        tipo, classe = next(iter(classes))
        chave = (cd, tipo, classe)
        ids = por_chave.get(chave, set())

        if len(ids) == 1:
            instrumento_id = str(next(iter(ids)))
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="ALIAS_EXISTENTE_FORTE",
                    cd_cvm=cd,
                    tipo_ativo=tipo,
                    classe=classe,
                    instrumento_id=instrumento_id,
                    chave_instrumento="",
                    fonte="FCA_2022_2024+TIPO+CLASSE",
                    detalhe="",
                )
            )
        elif len(ids) > 1:
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="REVISAO_MULTIPLOS_IDS_MESMA_CHAVE",
                    cd_cvm=cd,
                    tipo_ativo=tipo,
                    classe=classe,
                    instrumento_id="",
                    chave_instrumento="",
                    fonte="CATALOGO",
                    detalhe="ids=" + "|".join(str(x) for x in sorted(ids)),
                )
            )
        else:
            saida.append(
                ResultadoReconciliacaoHistorica(
                    ticker=ticker,
                    status="NOVO_INSTRUMENTO_HISTORICO_CANDIDATO",
                    cd_cvm=cd,
                    tipo_ativo=tipo,
                    classe=classe,
                    instrumento_id="",
                    chave_instrumento=f"{cd}|{tipo}|{classe}",
                    fonte="FCA_2022_2024+COTAHIST",
                    detalhe=(
                        "classe histórica não existe no catálogo promovido; "
                        f"IDs atuais do CD_CVM={','.join(str(x) for x in sorted(por_cd.get(cd, set())))}"
                    ),
                )
            )

    return saida


def serializar_resultados(
    resultados: Iterable[ResultadoReconciliacaoHistorica],
) -> list[dict[str, str]]:
    return [
        {
            "TICKER": x.ticker,
            "STATUS": x.status,
            "CD_CVM": x.cd_cvm,
            "TIPO_ATIVO": x.tipo_ativo,
            "CLASSE": x.classe,
            "INSTRUMENTO_ID": x.instrumento_id,
            "CHAVE_INSTRUMENTO": x.chave_instrumento,
            "FONTE": x.fonte,
            "DETALHE": x.detalhe,
        }
        for x in resultados
    ]

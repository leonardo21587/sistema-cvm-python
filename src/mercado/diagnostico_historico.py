from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import duckdb

from src.mercado.catalogo import carregar_catalogo_referencia
from src.mercado.identidade import (
    IdentidadeAmbigua,
    InstrumentoNaoEncontrado,
    resolver_instrumento,
)
from src.mercado.providers.cvm_fca import FcaValorMobiliario
from src.mercado.universo import resumir_cotahist_ano
from src.mercado.schema import criar_schema_identidade


@dataclass(frozen=True)
class ObservacaoTickerAno:
    ticker: str
    tipo_ativo: str
    classe: str
    primeira_data: date
    ultima_data: date
    pregoes: int
    isins: tuple[str, ...]
    especificacoes: tuple[str, ...]
    nomes_resumidos: tuple[str, ...]


def agregar_cotahist_ano(
    caminho: str | Path,
    *,
    ano: int,
) -> list[ObservacaoTickerAno]:
    """
    Reusa a classificação oficial da D.4 para manter somente ações/Units.

    Isso exclui FII, ETF, bônus, direitos, recibos e outros instrumentos cujo
    ticker pode ter formato semelhante, mas cuja ESPECIFICAÇÃO B3 não pertence
    ao escopo inicial.
    """
    resumos = resumir_cotahist_ano(
        caminho,
        ano=ano,
        tipo_mercado="010",
    )

    return [
        ObservacaoTickerAno(
            ticker=item.ticker,
            tipo_ativo=item.tipo_ativo,
            classe=item.classe,
            primeira_data=item.primeira_data,
            ultima_data=item.ultima_data,
            pregoes=item.pregoes,
            isins=item.isins,
            especificacoes=item.especificacoes,
            nomes_resumidos=(),
        )
        for item in sorted(
            resumos.values(),
            key=lambda x: x.ticker,
        )
    ]


def _resolver_seguro(
    con: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    data_ref: date,
) -> tuple[str, int | None]:
    try:
        return (
            "RESOLVIDO",
            resolver_instrumento(
                con,
                bolsa="B3",
                ticker=ticker,
                data_referencia=data_ref,
            ),
        )
    except InstrumentoNaoEncontrado:
        return "NAO_ENCONTRADO", None
    except IdentidadeAmbigua:
        return "AMBIGUO", None


def _mapa_isin_catalogo(
    con: duckdb.DuckDBPyConnection,
) -> dict[str, set[int]]:
    linhas = con.execute(
        """
        SELECT INSTRUMENTO_ID, VALOR
        FROM instrumentos_identificadores
        WHERE TIPO_IDENTIFICADOR = 'ISIN'
        """
    ).fetchall()

    mapa: dict[str, set[int]] = {}
    for instrumento_id, valor in linhas:
        mapa.setdefault(str(valor).strip().upper(), set()).add(
            int(instrumento_id)
        )
    return mapa


def _mapa_instrumentos_cd_cvm(
    con: duckdb.DuckDBPyConnection,
) -> tuple[
    dict[str, set[int]],
    dict[tuple[str, str, str], set[int]],
]:
    linhas = con.execute(
        """
        SELECT INSTRUMENTO_ID, CD_CVM, TIPO_ATIVO, CLASSE
        FROM instrumentos
        """
    ).fetchall()

    por_cd: dict[str, set[int]] = {}
    por_cd_classe: dict[tuple[str, str, str], set[int]] = {}

    for instrumento_id, cd_cvm, tipo, classe in linhas:
        cd = str(cd_cvm).strip().zfill(6)
        tipo = str(tipo).strip().upper()
        classe = str(classe).strip().upper()
        instrumento_id = int(instrumento_id)

        por_cd.setdefault(cd, set()).add(instrumento_id)
        por_cd_classe.setdefault(
            (cd, tipo, classe),
            set(),
        ).add(instrumento_id)

    return por_cd, por_cd_classe


def _fca_por_ticker(
    registros: Iterable[FcaValorMobiliario],
) -> dict[str, list[FcaValorMobiliario]]:
    mapa: dict[str, list[FcaValorMobiliario]] = {}
    for registro in registros:
        ticker = registro.codigo_negociacao.strip().upper()
        if not ticker:
            continue
        mapa.setdefault(ticker, []).append(registro)
    return mapa


def diagnosticar_ano(
    *,
    caminho_cotahist: str | Path,
    ano: int,
    reference_dir: str | Path,
    registros_fca: Iterable[FcaValorMobiliario],
    cd_cvm_sistema: set[str],
) -> list[dict[str, str]]:
    """
    Diagnóstico conservador: produz evidências e candidatos, nunca promove.

    Ordem de evidência:
    1) resolvedor temporal já promovido;
    2) ISIN exato já conhecido no catálogo;
    3) ticker exato no FCA do ano + CD_CVM dentro das empresas do sistema.

    O resultado CANDIDATO_* nunca equivale a aprovação automática.
    """
    observacoes = agregar_cotahist_ano(
        caminho_cotahist,
        ano=ano,
    )
    fca = _fca_por_ticker(registros_fca)

    con = duckdb.connect(":memory:")
    try:
        criar_schema_identidade(con)
        carregar_catalogo_referencia(
            con,
            reference_dir=reference_dir,
        )
        mapa_isin = _mapa_isin_catalogo(con)
        instrumentos_por_cd, instrumentos_por_cd_classe = (
            _mapa_instrumentos_cd_cvm(con)
        )

        saida: list[dict[str, str]] = []

        for obs in observacoes:
            status_ini, id_ini = _resolver_seguro(
                con,
                ticker=obs.ticker,
                data_ref=obs.primeira_data,
            )
            status_fim, id_fim = _resolver_seguro(
                con,
                ticker=obs.ticker,
                data_ref=obs.ultima_data,
            )

            ids_runtime = {
                x for x in (id_ini, id_fim)
                if x is not None
            }

            ids_isin: set[int] = set()
            for isin in obs.isins:
                ids_isin.update(mapa_isin.get(isin, set()))

            fca_ticker = fca.get(obs.ticker, [])
            cds_fca = sorted({
                r.cd_cvm.zfill(6)
                for r in fca_ticker
                if r.cd_cvm
            })
            cds_fca_sistema = [
                cd for cd in cds_fca
                if cd in cd_cvm_sistema
            ]
            ids_fca: set[int] = set()
            ids_fca_classe: set[int] = set()
            for cd in cds_fca_sistema:
                ids_fca.update(instrumentos_por_cd.get(cd, set()))
                ids_fca_classe.update(
                    instrumentos_por_cd_classe.get(
                        (cd, obs.tipo_ativo, obs.classe),
                        set(),
                    )
                )

            problemas: list[str] = []
            candidato_id = ""
            cd_cvm_candidato = ""

            if (
                status_ini == "RESOLVIDO"
                and status_fim == "RESOLVIDO"
                and len(ids_runtime) == 1
            ):
                status = "RESOLVIDO_CATALOGO"
                candidato_id = str(next(iter(ids_runtime)))
            elif "AMBIGUO" in {status_ini, status_fim}:
                status = "BLOQUEIO_AMBIGUIDADE_RUNTIME"
                problemas.append("RESOLUCAO_AMBIGUA")
            elif len(ids_isin) == 1:
                status = "CANDIDATO_ALIAS_ISIN"
                candidato_id = str(next(iter(ids_isin)))
            elif len(ids_isin) > 1:
                status = "BLOQUEIO_ISIN_MULTIPLO"
                problemas.append(
                    "ISIN_APONTA_MULTIPLOS_IDS:"
                    + "|".join(str(x) for x in sorted(ids_isin))
                )
            elif len(cds_fca_sistema) == 1:
                cd_cvm_candidato = cds_fca_sistema[0]
                if len(ids_fca_classe) == 1:
                    status = "CANDIDATO_FCA_ID_CLASSE"
                    candidato_id = str(next(iter(ids_fca_classe)))
                elif len(ids_fca_classe) > 1:
                    status = "BLOQUEIO_FCA_CLASSE_MULTIPLA"
                    problemas.append(
                        "CD_CVM_TIPO_CLASSE_COM_MULTIPLOS_IDS:"
                        + "|".join(
                            str(x) for x in sorted(ids_fca_classe)
                        )
                    )
                elif len(ids_fca) == 1:
                    status = "CANDIDATO_FCA_ID_UNICO"
                    candidato_id = str(next(iter(ids_fca)))
                else:
                    status = "CANDIDATO_FCA_CD_CVM"
                    if len(ids_fca) > 1:
                        problemas.append(
                            "CD_CVM_COM_MULTIPLOS_INSTRUMENTOS_SEM_MATCH_CLASSE:"
                            + "|".join(
                                str(x) for x in sorted(ids_fca)
                            )
                        )
            elif cds_fca and not cds_fca_sistema:
                status = "FORA_UNIVERSO_SISTEMA_FCA"
            elif len(cds_fca_sistema) > 1:
                status = "BLOQUEIO_FCA_MULTIPLO"
                problemas.append(
                    "FCA_MULTIPLOS_CD_CVM:"
                    + "|".join(cds_fca_sistema)
                )
            else:
                status = "SEM_EVIDENCIA_SUFICIENTE"

            if not cd_cvm_candidato and len(cds_fca_sistema) == 1:
                cd_cvm_candidato = cds_fca_sistema[0]

            saida.append(
                {
                    "ANO": str(ano),
                    "TICKER": obs.ticker,
                    "TIPO_ATIVO": obs.tipo_ativo,
                    "CLASSE": obs.classe,
                    "PRIMEIRA_DATA": obs.primeira_data.isoformat(),
                    "ULTIMA_DATA": obs.ultima_data.isoformat(),
                    "PREGOES": str(obs.pregoes),
                    "ISINS": "|".join(obs.isins),
                    "ESPECIFICACOES": "|".join(obs.especificacoes),
                    "NOMES_RESUMIDOS": "|".join(obs.nomes_resumidos),
                    "RUNTIME_INICIO": status_ini,
                    "RUNTIME_FIM": status_fim,
                    "ID_RUNTIME_INICIO": str(id_ini or ""),
                    "ID_RUNTIME_FIM": str(id_fim or ""),
                    "CD_CVM_FCA": "|".join(cds_fca),
                    "CD_CVM_CANDIDATO": cd_cvm_candidato,
                    "IDS_POR_ISIN": "|".join(
                        str(x) for x in sorted(ids_isin)
                    ),
                    "IDS_POR_CD_CVM": "|".join(
                        str(x) for x in sorted(ids_fca)
                    ),
                    "IDS_POR_CD_CVM_CLASSE": "|".join(
                        str(x) for x in sorted(ids_fca_classe)
                    ),
                    "CANDIDATO_INSTRUMENTO_ID": candidato_id,
                    "STATUS": status,
                    "PROBLEMAS": "|".join(problemas),
                }
            )

        return saida
    finally:
        con.close()


def escrever_diagnostico(
    caminho: str | Path,
    linhas: list[dict[str, str]],
) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    campos = [
        "ANO",
        "TICKER",
        "TIPO_ATIVO",
        "CLASSE",
        "PRIMEIRA_DATA",
        "ULTIMA_DATA",
        "PREGOES",
        "ISINS",
        "ESPECIFICACOES",
        "NOMES_RESUMIDOS",
        "RUNTIME_INICIO",
        "RUNTIME_FIM",
        "ID_RUNTIME_INICIO",
        "ID_RUNTIME_FIM",
        "CD_CVM_FCA",
        "CD_CVM_CANDIDATO",
        "IDS_POR_ISIN",
        "IDS_POR_CD_CVM",
        "IDS_POR_CD_CVM_CLASSE",
        "CANDIDATO_INSTRUMENTO_ID",
        "STATUS",
        "PROBLEMAS",
    ]

    with caminho.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=campos,
            delimiter=";",
        )
        escritor.writeheader()
        escritor.writerows(linhas)

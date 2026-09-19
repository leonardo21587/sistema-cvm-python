from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


FONTE_NOVOS = "D4_UNIVERSO_2025_GATE"


@dataclass(frozen=True)
class ResultadoCatalogoAmpliado:
    instrumentos: list[dict[str, str]]
    alocacoes: list[dict[str, str]]
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


def _normalizar_cd_cvm(valor: object) -> str:
    texto = _texto(valor)
    if texto.endswith(".0"):
        texto = texto[:-2]
    if not texto.isdigit() or len(texto) > 6:
        raise ValueError(f"CD_CVM invalido: {valor!r}")
    return texto.zfill(6)


def _normalizar_tipo(valor: object) -> str:
    tipo = _texto(valor).upper()
    if tipo not in {"ACAO", "UNIT"}:
        raise ValueError(f"TIPO_ATIVO invalido: {valor!r}")
    return tipo


def _normalizar_classe(tipo: str, valor: object) -> str:
    classe = _texto(valor).upper()
    classes = {"ON", "PN", "PNA", "PNB", "PNC", "PND", "UNIT"}
    if classe not in classes:
        raise ValueError(f"CLASSE invalida: {valor!r}")
    if tipo == "UNIT" and classe != "UNIT":
        raise ValueError("Instrumento UNIT exige CLASSE=UNIT.")
    if tipo == "ACAO" and classe == "UNIT":
        raise ValueError("ACAO nao pode usar CLASSE=UNIT.")
    return classe


def _chave(cd_cvm: str, tipo: str, classe: str) -> tuple[str, str, str]:
    return cd_cvm, tipo, classe


def _sobrepoe_janela_observada(
    instrumento: dict[str, str],
    *,
    inicio_observado: date,
    fim_observado_inclusivo: date,
) -> bool:
    """
    Instrumentos usam [DT_INICIO, DT_FIM).
    O grupo de 2025 usa primeira/ultima data observadas, ambas inclusivas.
    """
    inicio_instrumento = _data(instrumento["DT_INICIO"])
    fim_instrumento = _data_opcional(instrumento.get("DT_FIM", ""))

    return (
        inicio_instrumento <= fim_observado_inclusivo
        and (
            fim_instrumento is None
            or inicio_observado < fim_instrumento
        )
    )


def _copiar_instrumentos(
    instrumentos_existentes: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    saida = []
    ids = set()

    for bruto in instrumentos_existentes:
        instrumento_id = int(_texto(bruto["INSTRUMENTO_ID"]))
        if instrumento_id in ids:
            raise ValueError(
                f"INSTRUMENTO_ID duplicado no catalogo atual: {instrumento_id}"
            )
        ids.add(instrumento_id)

        tipo = _normalizar_tipo(bruto["TIPO_ATIVO"])
        classe = _normalizar_classe(tipo, bruto["CLASSE"])

        saida.append(
            {
                "INSTRUMENTO_ID": str(instrumento_id),
                "CD_CVM": _normalizar_cd_cvm(bruto["CD_CVM"]),
                "TIPO_ATIVO": tipo,
                "CLASSE": classe,
                "MOEDA": _texto(bruto.get("MOEDA", "BRL")).upper() or "BRL",
                "DT_INICIO": _data(bruto["DT_INICIO"]).isoformat(),
                "DT_FIM": (
                    _data_opcional(bruto.get("DT_FIM", "")).isoformat()
                    if _data_opcional(bruto.get("DT_FIM", ""))
                    else ""
                ),
                "STATUS": _texto(bruto["STATUS"]).upper(),
                "FONTE": _texto(bruto["FONTE"]),
            }
        )

    return sorted(saida, key=lambda x: int(x["INSTRUMENTO_ID"]))


def gerar_catalogo_ampliado(
    instrumentos_existentes: Iterable[dict[str, str]],
    grupos_candidatos: Iterable[dict[str, str]],
) -> ResultadoCatalogoAmpliado:
    """
    Expande o catalogo sem renumerar nenhum INSTRUMENTO_ID existente.

    Regras:
    - o grupo candidato precisa vir aprovado pelo gate do universo 2025;
    - um ID existente so e reutilizado quando ha exatamente um instrumento
      da mesma companhia/tipo/classe cuja vigencia sobrepoe a janela
      observada do grupo;
    - zero correspondencias -> novo ID sequencial acima do maior ID atual;
    - mais de uma correspondencia -> conflito bloqueante, sem alocacao;
    - a ordem do arquivo de entrada nao afeta a alocacao dos novos IDs.
    """
    existentes = _copiar_instrumentos(instrumentos_existentes)
    max_id_existente = max(
        (int(x["INSTRUMENTO_ID"]) for x in existentes),
        default=0,
    )

    por_chave: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for instrumento in existentes:
        chave = _chave(
            instrumento["CD_CVM"],
            instrumento["TIPO_ATIVO"],
            instrumento["CLASSE"],
        )
        por_chave.setdefault(chave, []).append(instrumento)

    grupos_normalizados: list[dict[str, object]] = []
    revisao: list[dict[str, str]] = []
    chaves_candidato = set()

    for bruto in grupos_candidatos:
        status = _texto(bruto.get("STATUS", "")).upper()
        problemas = _texto(bruto.get("PROBLEMAS", ""))

        cd_cvm = _normalizar_cd_cvm(bruto["CD_CVM"])
        tipo = _normalizar_tipo(bruto["TIPO_ATIVO"])
        classe = _normalizar_classe(tipo, bruto["CLASSE"])
        chave = _chave(cd_cvm, tipo, classe)

        inicio = _data(bruto["PRIMEIRA_DATA_2025"])
        fim = _data(bruto["ULTIMA_DATA_2025"])
        if fim < inicio:
            revisao.append(
                {
                    "NIVEL": "GRUPO",
                    "CHAVE": "|".join(chave),
                    "DETALHE": "JANELA_2025_INVALIDA",
                }
            )
            continue

        if status != "CANDIDATO_APROVADO" or problemas:
            revisao.append(
                {
                    "NIVEL": "GRUPO",
                    "CHAVE": "|".join(chave),
                    "DETALHE": (
                        f"GRUPO_NAO_APROVADO:STATUS={status};"
                        f"PROBLEMAS={problemas}"
                    ),
                }
            )
            continue

        if chave in chaves_candidato:
            revisao.append(
                {
                    "NIVEL": "GRUPO",
                    "CHAVE": "|".join(chave),
                    "DETALHE": "CHAVE_CANDIDATA_DUPLICADA",
                }
            )
            continue
        chaves_candidato.add(chave)

        grupos_normalizados.append(
            {
                "chave": chave,
                "cd_cvm": cd_cvm,
                "tipo": tipo,
                "classe": classe,
                "inicio": inicio,
                "fim": fim,
                "tickers": _texto(bruto.get("TICKERS_2025", "")),
                "isins": _texto(bruto.get("ISINS_2025", "")),
            }
        )

    grupos_normalizados.sort(
        key=lambda x: (
            x["cd_cvm"],
            x["tipo"],
            x["classe"],
            x["inicio"],
            x["tickers"],
        )
    )

    novos: list[dict[str, str]] = []
    alocacoes: list[dict[str, str]] = []
    proximo_id = max_id_existente + 1

    for grupo in grupos_normalizados:
        chave = grupo["chave"]
        candidatos_existentes = [
            instrumento
            for instrumento in por_chave.get(chave, [])
            if _sobrepoe_janela_observada(
                instrumento,
                inicio_observado=grupo["inicio"],
                fim_observado_inclusivo=grupo["fim"],
            )
        ]

        if len(candidatos_existentes) > 1:
            ids = "|".join(
                str(x["INSTRUMENTO_ID"])
                for x in sorted(
                    candidatos_existentes,
                    key=lambda x: int(x["INSTRUMENTO_ID"]),
                )
            )
            revisao.append(
                {
                    "NIVEL": "ALOCACAO",
                    "CHAVE": "|".join(chave),
                    "DETALHE": f"MULTIPLOS_IDS_EXISTENTES_SOBREPOSTOS:{ids}",
                }
            )
            continue

        if len(candidatos_existentes) == 1:
            instrumento_id = int(candidatos_existentes[0]["INSTRUMENTO_ID"])
            origem = "REUTILIZADO"
        else:
            instrumento_id = proximo_id
            proximo_id += 1
            origem = "NOVO"

            novo = {
                "INSTRUMENTO_ID": str(instrumento_id),
                "CD_CVM": grupo["cd_cvm"],
                "TIPO_ATIVO": grupo["tipo"],
                "CLASSE": grupo["classe"],
                "MOEDA": "BRL",
                "DT_INICIO": grupo["inicio"].isoformat(),
                "DT_FIM": "",
                "STATUS": "ATIVO",
                "FONTE": FONTE_NOVOS,
            }
            novos.append(novo)
            por_chave.setdefault(chave, []).append(novo)

        alocacoes.append(
            {
                "CHAVE_CANDIDATO": "|".join(chave),
                "INSTRUMENTO_ID": str(instrumento_id),
                "ORIGEM_ID": origem,
                "CD_CVM": grupo["cd_cvm"],
                "TIPO_ATIVO": grupo["tipo"],
                "CLASSE": grupo["classe"],
                "PRIMEIRA_DATA_2025": grupo["inicio"].isoformat(),
                "ULTIMA_DATA_2025": grupo["fim"].isoformat(),
                "TICKERS_2025": grupo["tickers"],
                "ISINS_2025": grupo["isins"],
            }
        )

    instrumentos_finais = sorted(
        [*existentes, *novos],
        key=lambda x: int(x["INSTRUMENTO_ID"]),
    )

    ids_finais = [int(x["INSTRUMENTO_ID"]) for x in instrumentos_finais]
    ids_novos = [int(x["INSTRUMENTO_ID"]) for x in novos]

    if len(ids_finais) != len(set(ids_finais)):
        revisao.append(
            {
                "NIVEL": "CATALOGO",
                "CHAVE": "INSTRUMENTO_ID",
                "DETALHE": "ID_DUPLICADO_APOS_EXPANSAO",
            }
        )

    if ids_novos:
        esperado = list(range(max_id_existente + 1, max(ids_novos) + 1))
        if sorted(ids_novos) != esperado:
            revisao.append(
                {
                    "NIVEL": "CATALOGO",
                    "CHAVE": "INSTRUMENTO_ID",
                    "DETALHE": "NOVOS_IDS_NAO_SEQUENCIAIS",
                }
            )

    ids_existentes_antes = {
        int(x["INSTRUMENTO_ID"]): x
        for x in existentes
    }
    ids_existentes_depois = {
        int(x["INSTRUMENTO_ID"]): x
        for x in instrumentos_finais
        if int(x["INSTRUMENTO_ID"]) <= max_id_existente
    }
    if ids_existentes_antes != ids_existentes_depois:
        revisao.append(
            {
                "NIVEL": "CATALOGO",
                "CHAVE": "PRESERVACAO_IDS",
                "DETALHE": "CATALOGO_EXISTENTE_FOI_ALTERADO",
            }
        )

    gate_aprovado = (
        not revisao
        and len(alocacoes) == len(grupos_normalizados)
        and len(chaves_candidato) == len(grupos_normalizados)
    )

    return ResultadoCatalogoAmpliado(
        instrumentos=instrumentos_finais,
        alocacoes=alocacoes,
        revisao=revisao,
        gate_aprovado=gate_aprovado,
    )

from __future__ import annotations

import re
import unicodedata


CLASSES_ACAO = {"ON", "PN", "PNA", "PNB", "PNC", "PND"}


def _normalizar_texto(valor: object) -> str:
    texto = str(valor or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return " ".join(texto.split())


def _classes_cotahist(especificacoes: object) -> set[str]:
    """
    Extrai classe econômica do campo ESPECIFICACAO do COTAHIST.

    Exemplos observados no layout:
    - ON / ON NM / ON N1 / ON N2
    - PN / PN N1 / PN N2
    - PNA / PNB / PNC / PND
    - UNT / UNIT para units

    Sufixos de segmento/listagem são ignorados.
    """
    if isinstance(especificacoes, str):
        itens = [
            item
            for item in especificacoes.split("|")
            if item.strip()
        ]
    else:
        try:
            itens = list(especificacoes or [])
        except TypeError:
            itens = [especificacoes]

    classes = set()

    for item in itens:
        texto = _normalizar_texto(item)
        compacto = re.sub(r"[^A-Z0-9]", "", texto)

        if compacto.startswith("PNA"):
            classes.add("PNA")
        elif compacto.startswith("PNB"):
            classes.add("PNB")
        elif compacto.startswith("PNC"):
            classes.add("PNC")
        elif compacto.startswith("PND"):
            classes.add("PND")
        elif compacto.startswith("PN"):
            classes.add("PN")
        elif compacto.startswith("ON"):
            classes.add("ON")
        elif compacto.startswith("UNT") or compacto.startswith("UNIT"):
            classes.add("UNIT")

    return classes


def inferir_tipo_classe(
    *,
    ticker: str,
    valor_mobiliario: object = "",
    sigla_classe_preferencial: object = "",
    classe_preferencial: object = "",
    composicao_unit: object = "",
    especificacoes_cotahist: object = "",
) -> tuple[str | None, str | None]:
    """
    Infere TIPO_ATIVO e CLASSE combinando FCA + COTAHIST.

    O ticker sozinho define apenas o escopo inicial. Para preferenciais,
    a classe vem primeiro do FCA e, quando ausente/inconsistente, do
    campo ESPECIFICACAO observado no COTAHIST.

    Nenhuma regra assume que os finais 5/6/7/8 equivalem automaticamente
    a PNA/PNB/PNC/PND.
    """
    ticker = _normalizar_texto(ticker)
    valor = _normalizar_texto(valor_mobiliario)
    sigla = _normalizar_texto(sigla_classe_preferencial)
    classe_extenso = _normalizar_texto(classe_preferencial)
    composicao = _normalizar_texto(composicao_unit)
    classes_b3 = _classes_cotahist(especificacoes_cotahist)

    if ticker.endswith("11"):
        if (
            "UNIT" in valor
            or "UNIT" in composicao
            or "UNT" in classes_b3
            or "UNIT" in classes_b3
        ):
            return "UNIT", "UNIT"
        return None, None

    if ticker.endswith("3"):
        if classes_b3 and classes_b3 != {"ON"}:
            return None, None
        return "ACAO", "ON"

    if ticker[-1:] in {"4", "5", "6", "7", "8"}:
        if sigla in CLASSES_ACAO - {"ON"}:
            return "ACAO", sigla

        mapa_extenso = {
            "PREFERENCIAL": "PN",
            "ACAO PREFERENCIAL": "PN",
            "ACOES PREFERENCIAIS": "PN",
            "PREFERENCIAL CLASSE A": "PNA",
            "ACAO PREFERENCIAL CLASSE A": "PNA",
            "ACOES PREFERENCIAIS CLASSE A": "PNA",
            "PREFERENCIAL CLASSE B": "PNB",
            "ACAO PREFERENCIAL CLASSE B": "PNB",
            "ACOES PREFERENCIAIS CLASSE B": "PNB",
            "PREFERENCIAL CLASSE C": "PNC",
            "ACAO PREFERENCIAL CLASSE C": "PNC",
            "ACOES PREFERENCIAIS CLASSE C": "PNC",
            "PREFERENCIAL CLASSE D": "PND",
            "ACAO PREFERENCIAL CLASSE D": "PND",
            "ACOES PREFERENCIAIS CLASSE D": "PND",
        }
        if classe_extenso in mapa_extenso:
            return "ACAO", mapa_extenso[classe_extenso]

        classes_pref_b3 = classes_b3 & {"PN", "PNA", "PNB", "PNC", "PND"}
        if len(classes_pref_b3) == 1:
            return "ACAO", next(iter(classes_pref_b3))

        return None, None

    return None, None

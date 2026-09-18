from __future__ import annotations

from pathlib import Path
import py_compile


ROOT_DIR = Path(__file__).resolve().parent.parent
APP = ROOT_DIR / "app.py"


def main() -> None:
    print("=" * 78)
    print("SISTEMA CVM — TESTE INTERFACE FINANCEIRA — ETAPA B.3")
    print("=" * 78)

    if not APP.exists():
        raise FileNotFoundError(APP)

    py_compile.compile(
        str(APP),
        doraise=True,
    )

    texto = APP.read_text(
        encoding="utf-8"
    )

    testes = {
        "marcador_b3": (
            "# === B3_UI_FINANCEIRA ==="
            in texto
        ),
        "painel_financeiro_roa_roe": (
            "grafico_rentabilidade_financeira"
            in texto
            and '"ROA",' in texto
            and '"ROE",' in texto
        ),
        "expander_auditoria_na": (
            "Indicadores tradicionais não aplicáveis — auditoria metodológica"
            in texto
        ),
        "filtro_na": (
            '"APLICABILIDADE"'
            in texto
            and '"NAO_APLICAVEL"'
            in texto
        ),
        "detalhamento_financeira_restrito": (
            'else ORDEM_INDICADORES'
            in texto
        ),
        "camada_b2_preservada": (
            "## Indicadores setoriais — Financeiro"
            in texto
            and '"CAP_CONTABIL"' in texto
            and '"RBI_ATIVO_MEDIO"' in texto
        ),
        "modelo_padrao_preservado": (
            '"IPL"' in texto
            and '"PCT"' in texto
            and '"CE"' in texto
            and '"EFSAT"' in texto
            and '"LG"' in texto
            and '"LC"' in texto
            and '"LS"' in texto
            and '"ICJ"' in texto
            and '"GA"' in texto
            and '"RSV"' in texto
        ),
    }

    falhas = []

    for nome, ok in testes.items():
        print(
            f"{nome:38s} "
            f"{'OK' if ok else 'FALHA'}"
        )

        if not ok:
            falhas.append(nome)

    if falhas:
        raise AssertionError(
            "Falhas B.3: "
            + ", ".join(falhas)
        )

    print()
    print(
        "RESULTADO: APROVADO — interface B.3 "
        "estruturalmente válida."
    )
    print()
    print("Rode em seguida:")
    print(r"python tests\test_indicadores_financeiros.py")
    print()
    print("Depois teste visualmente:")
    print("streamlit run app.py")


if __name__ == "__main__":
    main()

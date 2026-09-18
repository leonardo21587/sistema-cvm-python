from __future__ import annotations

from pathlib import Path
import py_compile


ROOT_DIR = Path(__file__).resolve().parent.parent
APP = ROOT_DIR / "app.py"
MODULO = ROOT_DIR / "src" / "indicadores_financeiros.py"


def main() -> None:
    print("=" * 78)
    print("SISTEMA CVM — TESTE INTEGRAÇÃO FINANCEIRA — ETAPA B.2")
    print("=" * 78)

    if not APP.exists():
        raise FileNotFoundError(APP)

    if not MODULO.exists():
        raise FileNotFoundError(MODULO)

    py_compile.compile(
        str(APP),
        doraise=True,
    )

    py_compile.compile(
        str(MODULO),
        doraise=True,
    )

    texto = APP.read_text(
        encoding="utf-8"
    )

    testes = {
        "import_motor_setorial": (
            "from src.indicadores_financeiros import"
            in texto
        ),
        "cache_setorial": (
            "def carregar_indicadores_financeiros_setoriais("
            in texto
        ),
        "painel_setorial": (
            "## Indicadores setoriais — Financeiro"
            in texto
        ),
        "capitalizacao_funding": (
            "### Capitalização e Funding"
            in texto
        ),
        "crescimento": (
            '"CRESC_ATIVO"' in texto
            and '"CRESC_PL"' in texto
            and '"CRESC_LL"' in texto
        ),
        "intermediacao": (
            '"RBI_ATIVO_MEDIO"' in texto
            and '"PRETRIB_ATIVO_MEDIO"' in texto
        ),
        "contador_9": (
            "qtd_indicadores_financeiros_disponiveis"
            in texto
            and '/ 9"' in texto
        ),
        "tradicional_preservado": (
            'f"{qtd_indicadores_aplicaveis} / 12"'
            in texto
        ),
    }

    falhas = [
        nome
        for nome, ok in testes.items()
        if not ok
    ]

    for nome, ok in testes.items():
        print(
            f"{nome:35s} "
            f"{'OK' if ok else 'FALHA'}"
        )

    if falhas:
        raise AssertionError(
            "Falhas B.2: "
            + ", ".join(falhas)
        )

    print()
    print(
        "RESULTADO: APROVADO — integração B.2 "
        "presente e sintaticamente válida."
    )
    print()
    print(
        "Agora rode novamente:"
    )
    print(
        r"python tests\test_indicadores_financeiros.py"
    )
    print()
    print(
        "Depois:"
    )
    print(
        "streamlit run app.py"
    )


if __name__ == "__main__":
    main()

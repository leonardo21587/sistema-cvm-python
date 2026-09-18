from __future__ import annotations

from pathlib import Path
import shutil


ROOT_DIR = Path(__file__).resolve().parent.parent
APP = ROOT_DIR / "app.py"
BACKUP = ROOT_DIR / "app_pre_b2_financeira.py"
MARCADOR = "# === B2_INDICADORES_FINANCEIROS ==="


def substituir_unico(texto: str, antigo: str, novo: str, descricao: str) -> str:
    quantidade = texto.count(antigo)
    if quantidade != 1:
        raise RuntimeError(
            f"{descricao}: esperado exatamente 1 ponto de substituição; "
            f"encontrados {quantidade}."
        )
    return texto.replace(antigo, novo, 1)


def main() -> None:
    print("=" * 78)
    print("SISTEMA CVM — ETAPA B.2 — INTEGRAÇÃO VISUAL FINANCEIRA")
    print("=" * 78)

    if not APP.exists():
        raise FileNotFoundError(f"app.py não encontrado: {APP}")

    texto = APP.read_text(encoding="utf-8")

    if MARCADOR in texto:
        print()
        print("B.2 já está aplicada ao app.py. Nenhuma alteração realizada.")
        return

    modulo = ROOT_DIR / "src" / "indicadores_financeiros.py"
    if not modulo.exists():
        raise FileNotFoundError(
            "src\\indicadores_financeiros.py não encontrado. "
            "Conclua primeiro a ETAPA B.1."
        )

    if not BACKUP.exists():
        shutil.copy2(APP, BACKUP)
        print(f"Backup criado: {BACKUP}")
    else:
        print(f"Backup pré-B.2 já existe: {BACKUP}")

    antigo = '''from src.indicadores import (
    quadro_indicadores,
    detalhar_indicador,
    validar_dupont,
)

from src.relatorio import (
'''

    novo = '''from src.indicadores import (
    quadro_indicadores,
    detalhar_indicador,
    validar_dupont,
)

# === B2_INDICADORES_FINANCEIROS ===
from src.indicadores_financeiros import (
    INDICADORES_FINANCEIROS,
    NOMES as NOMES_INDICADORES_FINANCEIROS,
    calcular_indicadores_financeiros,
)

from src.relatorio import (
'''

    texto = substituir_unico(
        texto, antigo, novo, "Import do motor financeiro setorial"
    )

    antigo = '''def formatar_raw(valor):
'''

    novo = r'''def formatar_percentual_setorial(
    valor,
    status="OK",
):
    status = str(status).strip().upper()

    if status in {"N/A", "N/D"}:
        return status

    if valor is None or pd.isna(valor):
        return "N/D"

    return (
        f"{float(valor) * 100:.2f}%"
        .replace(".", ",")
    )


def tabela_indicadores_financeiros_setoriais(
    dados,
    grupo,
    anos_desc,
):
    if dados is None or dados.empty:
        return pd.DataFrame()

    parte = dados.loc[
        dados["GRUPO"].eq(grupo)
    ].copy()

    if parte.empty:
        return pd.DataFrame()

    ordem = {
        codigo: indice
        for indice, codigo in enumerate(
            INDICADORES_FINANCEIROS
        )
    }

    codigos = (
        parte[
            ["INDICADOR", "NOME", "UNIDADE", "FORMULA"]
        ]
        .drop_duplicates(subset=["INDICADOR"])
        .assign(
            _ORDEM=lambda d: d["INDICADOR"].map(ordem)
        )
        .sort_values("_ORDEM")
    )

    registros = []

    for _, meta in codigos.iterrows():
        codigo = str(meta["INDICADOR"])

        registro = {
            "Sigla": codigo,
            "Indicador": meta["NOME"],
            "Unidade": meta["UNIDADE"],
        }

        for ano in anos_desc:
            linha_ano = parte.loc[
                parte["INDICADOR"].eq(codigo)
                & parte["ANO"].eq(int(ano))
            ]

            if linha_ano.empty:
                registro[str(ano)] = "N/D"
                continue

            linha = linha_ano.iloc[0]

            registro[str(ano)] = (
                formatar_percentual_setorial(
                    linha["VALOR"],
                    linha["STATUS"],
                )
            )

        recente = parte.loc[
            parte["INDICADOR"].eq(codigo)
            & parte["ANO"].eq(max(anos_desc))
        ]

        if recente.empty:
            registro["Status recente"] = "N/D"
            registro["Observação"] = "Exercício recente não disponível."
        else:
            linha_rec = recente.iloc[0]
            registro["Status recente"] = str(
                linha_rec["STATUS"]
            )

            motivo = linha_rec.get(
                "MOTIVO",
                None,
            )

            registro["Observação"] = (
                ""
                if (
                    motivo is None
                    or pd.isna(motivo)
                )
                else str(motivo)
            )

        registros.append(registro)

    return pd.DataFrame(registros)


def exibir_cards_financeiros_setoriais(
    dados,
    codigos,
    ano_base,
    ano_recente,
):
    if dados is None or dados.empty:
        return

    colunas = st.columns(len(codigos))

    for indice, codigo in enumerate(codigos):
        recente = dados.loc[
            dados["INDICADOR"].eq(codigo)
            & dados["ANO"].eq(int(ano_recente))
        ]

        base = dados.loc[
            dados["INDICADOR"].eq(codigo)
            & dados["ANO"].eq(int(ano_base))
        ]

        with colunas[indice]:
            if recente.empty:
                st.metric(
                    label=(
                        f"{codigo} — "
                        f"{NOMES_INDICADORES_FINANCEIROS[codigo]}"
                    ),
                    value="N/D",
                )
                st.caption("Exercício recente não disponível.")
                continue

            linha_rec = recente.iloc[0]
            status = str(
                linha_rec["STATUS"]
            ).strip().upper()

            valor_fmt = formatar_percentual_setorial(
                linha_rec["VALOR"],
                status,
            )

            st.metric(
                label=(
                    f"{codigo} — "
                    f"{NOMES_INDICADORES_FINANCEIROS[codigo]}"
                ),
                value=valor_fmt,
            )

            if status != "OK":
                motivo = linha_rec.get(
                    "MOTIVO",
                    None,
                )

                st.caption(
                    str(motivo)
                    if (
                        motivo is not None
                        and not pd.isna(motivo)
                    )
                    else status
                )
                continue

            if codigo in {
                "CRESC_ATIVO",
                "CRESC_PL",
                "CRESC_LL",
            }:
                st.caption(
                    f"Variação {ano_recente - 1} → {ano_recente}."
                )
                continue

            if base.empty:
                st.caption(f"Valor de {ano_recente}.")
                continue

            linha_base = base.iloc[0]

            if (
                str(linha_base["STATUS"]).strip().upper() != "OK"
                or pd.isna(linha_base["VALOR"])
            ):
                st.caption(f"Valor de {ano_recente}.")
                continue

            delta_pp = (
                (
                    float(linha_rec["VALOR"])
                    - float(linha_base["VALOR"])
                )
                * 100
            )

            st.caption(
                (
                    f"vs. {ano_base}: "
                    f"{delta_pp:+.2f} p.p."
                ).replace(".", ",")
            )


def formatar_raw(valor):
'''

    texto = substituir_unico(
        texto, antigo, novo, "Funções de renderização setorial"
    )

    antigo = '''@st.cache_data(show_spinner=False)
def carregar_detalhe_indicador(
'''

    novo = '''@st.cache_data(show_spinner=False)
def carregar_indicadores_financeiros_setoriais(
    cd_cvm,
    anos_tuple,
):

    return calcular_indicadores_financeiros(
        cd_cvm,
        anos=list(
            anos_tuple
        ),
    )


@st.cache_data(show_spinner=False)
def carregar_detalhe_indicador(
'''

    texto = substituir_unico(
        texto, antigo, novo, "Cache da camada setorial"
    )

    antigo = '''    if tratamento_setorial:
        st.info(
'''

    novo = '''    indicadores_fin_setoriais = pd.DataFrame()
    erro_indicadores_fin_setoriais = None
    qtd_indicadores_financeiros_disponiveis = 0

    if "FINANCEIRA" in layouts_detectados:
        try:
            indicadores_fin_setoriais = (
                carregar_indicadores_financeiros_setoriais(
                    cd_cvm,
                    anos_tuple,
                )
            )

            setoriais_recentes = (
                indicadores_fin_setoriais.loc[
                    indicadores_fin_setoriais["ANO"].eq(
                        int(ano_recente)
                    )
                    & indicadores_fin_setoriais["STATUS"].eq(
                        "OK"
                    )
                ]
            )

            qtd_setoriais_ok = int(
                setoriais_recentes["INDICADOR"].nunique()
            )

            tradicionais_fin = (
                quadro_inds.loc[
                    quadro_inds["INDICADOR"].isin(
                        ["ROA", "ROE"]
                    )
                ]
            )

            qtd_trad_fin_ok = 0

            if ano_recente in tradicionais_fin.columns:
                qtd_trad_fin_ok = int(
                    tradicionais_fin[ano_recente]
                    .notna()
                    .sum()
                )

            qtd_indicadores_financeiros_disponiveis = (
                qtd_setoriais_ok
                + qtd_trad_fin_ok
            )

        except Exception as erro:
            erro_indicadores_fin_setoriais = erro

    if tratamento_setorial:
        st.info(
'''

    texto = substituir_unico(
        texto, antigo, novo, "Carga da camada financeira"
    )

    antigo = '''        st.caption(
            "Síntese visual dos 12 indicadores financeiros. "
            "Os valores são provenientes diretamente do "
            "motor de indicadores e não são recalculados "
            "pelo painel."
        )
'''

    novo = '''        st.caption(
            "Síntese visual dos indicadores financeiros "
            "aplicáveis ao layout contábil. "
            "Os valores são provenientes diretamente dos "
            "motores validados e não são recalculados "
            "pelo painel."
        )
'''

    texto = substituir_unico(
        texto, antigo, novo, "Legenda do painel"
    )

    antigo = '''                (
                    f"{qtd_indicadores_aplicaveis} / 12"
                ),
'''

    novo = '''                (
                    (
                        f"{qtd_indicadores_financeiros_disponiveis} / 9"
                    )
                    if (
                        "FINANCEIRA"
                        in layouts_detectados
                    )
                    else (
                        f"{qtd_indicadores_aplicaveis} / 12"
                    )
                ),
'''

    texto = substituir_unico(
        texto, antigo, novo, "Contador do painel"
    )

    antigo = '''        # ----------------------------------------------------
        # ESTRUTURA
        # ----------------------------------------------------

        st.markdown(
            "## Estrutura de Capital"
        )
'''

    novo = '''        # ----------------------------------------------------
        # INDICADORES SETORIAIS — FINANCEIRO
        # ----------------------------------------------------

        if (
            "FINANCEIRA"
            in layouts_detectados
        ):
            st.markdown(
                "## Indicadores setoriais — Financeiro"
            )

            if erro_indicadores_fin_setoriais is not None:
                st.warning(
                    "A camada setorial financeira "
                    "não pôde ser carregada."
                )

                with st.expander(
                    "Detalhes técnicos"
                ):
                    st.exception(
                        erro_indicadores_fin_setoriais
                    )

            elif indicadores_fin_setoriais.empty:
                st.info(
                    "Indicadores setoriais financeiros "
                    "não disponíveis para o período."
                )

            else:
                st.markdown(
                    "### Capitalização e Funding"
                )

                exibir_cards_financeiros_setoriais(
                    indicadores_fin_setoriais,
                    [
                        "CAP_CONTABIL",
                        "PF_ATIVO",
                    ],
                    ano_base,
                    ano_recente,
                )

                st.markdown(
                    "### Crescimento"
                )

                exibir_cards_financeiros_setoriais(
                    indicadores_fin_setoriais,
                    [
                        "CRESC_ATIVO",
                        "CRESC_PL",
                        "CRESC_LL",
                    ],
                    ano_base,
                    ano_recente,
                )

                st.markdown(
                    "### Intermediação e Rentabilidade"
                )

                exibir_cards_financeiros_setoriais(
                    indicadores_fin_setoriais,
                    [
                        "RBI_ATIVO_MEDIO",
                        "PRETRIB_ATIVO_MEDIO",
                    ],
                    ano_base,
                    ano_recente,
                )

                st.caption(
                    "Capitalização Contábil não representa "
                    "capital regulatório/Basileia. "
                    "RBI/Ativo Médio não representa NIM. "
                    "Crescimentos utilizam apenas períodos "
                    "com base comparável."
                )

            st.divider()

            st.markdown(
                "## Indicadores tradicionais — referência metodológica"
            )

            st.caption(
                "ROA e ROE permanecem aplicáveis pelo motor original. "
                "Os demais indicadores tradicionais incompatíveis "
                "continuam classificados como N/A."
            )

        # ----------------------------------------------------
        # ESTRUTURA
        # ----------------------------------------------------

        st.markdown(
            "## Estrutura de Capital"
        )
'''

    texto = substituir_unico(
        texto, antigo, novo, "Cards setoriais do painel"
    )

    antigo = '''        if quadro_inds.empty:

            st.warning(
                "Indicadores não disponíveis."
            )

        else:
'''

    novo = '''        if (
            "FINANCEIRA"
            in layouts_detectados
        ):
            st.markdown(
                "## Indicadores setoriais — Financeiro"
            )

            if erro_indicadores_fin_setoriais is not None:
                st.warning(
                    "Não foi possível carregar "
                    "a camada setorial financeira."
                )

            elif indicadores_fin_setoriais.empty:
                st.info(
                    "Indicadores setoriais financeiros "
                    "não disponíveis."
                )

            else:
                for grupo_fin in [
                    "Capitalização e Funding",
                    "Crescimento",
                    "Intermediação e Rentabilidade",
                ]:
                    st.markdown(
                        f"### {grupo_fin}"
                    )

                    tabela_fin = (
                        tabela_indicadores_financeiros_setoriais(
                            indicadores_fin_setoriais,
                            grupo_fin,
                            anos_desc,
                        )
                    )

                    st.dataframe(
                        tabela_fin,
                        use_container_width=True,
                        hide_index=True,
                    )

                st.caption(
                    "N/D indica dado necessário indisponível. "
                    "N/A indica taxa não interpretável "
                    "pela regra metodológica, como mudança "
                    "de sinal do Lucro Líquido."
                )

            st.divider()

            st.markdown(
                "## Indicadores tradicionais — referência metodológica"
            )

        if quadro_inds.empty:

            st.warning(
                "Indicadores não disponíveis."
            )

        else:
'''

    texto = substituir_unico(
        texto, antigo, novo, "Tabela setorial na aba Indicadores"
    )

    compile(texto, str(APP), "exec")

    APP.write_text(
        texto,
        encoding="utf-8",
    )

    print()
    print("B.2 aplicada com sucesso.")
    print(f"app.py: {APP}")
    print(f"backup: {BACKUP}")
    print()
    print("Preservados sem alteração:")
    print("- src\\indicadores.py")
    print("- src\\validacao.py")
    print("- src\\relatorio.py")
    print("- src\\graficos.py")
    print("- src\\exportacao.py")
    print("- ETL / DuckDB")
    print()
    print("Próximo comando:")
    print(r"python tests\test_integracao_financeira_b2.py")


if __name__ == "__main__":
    main()

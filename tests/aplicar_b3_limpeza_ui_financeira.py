from __future__ import annotations

"""
ETAPA B.3 — limpeza da interface para layout FINANCEIRA.

Pré-requisito:
- ETAPA B.2 já aplicada.

Este patch:
- cria backup de app.py;
- no Painel FINANCEIRA, remove da visualização principal os blocos tradicionais
  incompatíveis (IPL/PCT/CE/EFSAT/LG/LC/LS/ICJ/GA/RSV);
- mantém ROA e ROE visíveis como rentabilidade aplicável;
- na aba Indicadores, mostra os 7 setoriais + ROA/ROE;
- move os indicadores tradicionais N/A para um expander de auditoria;
- restringe o detalhamento tradicional a ROA/ROE no layout FINANCEIRA;
- NÃO altera fórmulas, ETL, banco, relatório, exportação ou motores de cálculo.
"""

from pathlib import Path
import shutil


ROOT_DIR = Path(__file__).resolve().parent.parent
APP = ROOT_DIR / "app.py"
BACKUP = ROOT_DIR / "app_pre_b3_financeira.py"

MARCADOR_B2 = "# === B2_INDICADORES_FINANCEIROS ==="
MARCADOR_B3 = "# === B3_UI_FINANCEIRA ==="


def substituir_unico(
    texto: str,
    antigo: str,
    novo: str,
    descricao: str,
) -> str:
    quantidade = texto.count(antigo)

    if quantidade != 1:
        raise RuntimeError(
            f"{descricao}: esperado exatamente 1 ponto; "
            f"encontrados {quantidade}."
        )

    return texto.replace(
        antigo,
        novo,
        1,
    )


def main() -> None:
    print("=" * 78)
    print("SISTEMA CVM — ETAPA B.3 — LIMPEZA DA INTERFACE FINANCEIRA")
    print("=" * 78)

    if not APP.exists():
        raise FileNotFoundError(
            f"app.py não encontrado: {APP}"
        )

    texto = APP.read_text(
        encoding="utf-8"
    )

    if MARCADOR_B3 in texto:
        print()
        print("B.3 já aplicada. Nenhuma alteração realizada.")
        return

    if MARCADOR_B2 not in texto:
        raise RuntimeError(
            "A integração B.2 não foi encontrada no app.py. "
            "Aplique B.2 antes da B.3."
        )

    if not BACKUP.exists():
        shutil.copy2(
            APP,
            BACKUP,
        )
        print(
            f"Backup criado: {BACKUP}"
        )
    else:
        print(
            f"Backup pré-B.3 já existe: {BACKUP}"
        )

    antigo = """        # ----------------------------------------------------
        # ESTRUTURA
        # ----------------------------------------------------

        st.markdown(
            "## Estrutura de Capital"
        )

        exibir_cards_dashboard(
            cards_dashboard,
            [
                "IPL",
                "PCT",
                "CE",
                "EFSAT",
            ],
            ano_base,
        )

        exibir_grafico_dashboard(
            graficos_dashboard[
                "estrutura"
            ],
            key="grafico_estrutura_dashboard",
        )

        st.caption(
            "IPL, PCT, CE e EFSAT são apresentados "
            "em percentual. PCT, CE e EFSAT exigem "
            "interpretação contextual."
        )


        st.divider()


        # ----------------------------------------------------
        # LIQUIDEZ
        # ----------------------------------------------------

        st.markdown(
            "## Liquidez"
        )

        exibir_cards_dashboard(
            cards_dashboard,
            [
                "LG",
                "LC",
                "LS",
                "ICJ",
            ],
            ano_base,
        )

        coluna_liquidez, coluna_icj = (
            st.columns(
                [
                    2,
                    1,
                ]
            )
        )

        with coluna_liquidez:

            exibir_grafico_dashboard(
                graficos_dashboard[
                    "liquidez"
                ],
                key="grafico_liquidez_dashboard",
            )

        with coluna_icj:

            exibir_grafico_dashboard(
                graficos_dashboard[
                    "icj"
                ],
                key="grafico_icj_dashboard",
            )

        st.caption(
            "LG, LC e LS são razões. "
            "O ICJ é apresentado separadamente "
            "por possuir escala própria em vezes."
        )


        st.divider()


        # ----------------------------------------------------
        # DESEMPENHO
        # ----------------------------------------------------

        st.markdown(
            "## Lucratividade e Desempenho"
        )

        exibir_cards_dashboard(
            cards_dashboard,
            [
                "GA",
                "RSV",
                "ROA",
                "ROE",
            ],
            ano_base,
        )

        coluna_rentabilidade, coluna_ga = (
            st.columns(
                [
                    2,
                    1,
                ]
            )
        )

        with coluna_rentabilidade:

            exibir_grafico_dashboard(
                graficos_dashboard[
                    "rentabilidade"
                ],
                key="grafico_rentabilidade_dashboard",
            )

        with coluna_ga:

            exibir_grafico_dashboard(
                graficos_dashboard[
                    "ga"
                ],
                key="grafico_ga_dashboard",
            )

        st.caption(
            "RSV, ROA e ROE são percentuais. "
            "O Giro do Ativo é apresentado separadamente "
            "por utilizar unidade em vezes."
        )


        st.divider()
"""

    novo = """        # === B3_UI_FINANCEIRA ===
        if (
            "FINANCEIRA"
            in layouts_detectados
        ):
            st.markdown(
                "## Rentabilidade"
            )

            exibir_cards_dashboard(
                cards_dashboard,
                [
                    "ROA",
                    "ROE",
                ],
                ano_base,
            )

            exibir_grafico_dashboard(
                graficos_dashboard[
                    "rentabilidade"
                ],
                key="grafico_rentabilidade_financeira",
            )

            st.caption(
                "ROA e ROE permanecem calculados pelo "
                "motor original já validado. Os demais "
                "indicadores tradicionais incompatíveis "
                "ficam disponíveis apenas na auditoria metodológica."
            )

            st.divider()

        else:
            st.markdown(
                "## Estrutura de Capital"
            )

            exibir_cards_dashboard(
                cards_dashboard,
                [
                    "IPL",
                    "PCT",
                    "CE",
                    "EFSAT",
                ],
                ano_base,
            )

            exibir_grafico_dashboard(
                graficos_dashboard[
                    "estrutura"
                ],
                key="grafico_estrutura_dashboard",
            )

            st.caption(
                "IPL, PCT, CE e EFSAT são apresentados "
                "em percentual. PCT, CE e EFSAT exigem "
                "interpretação contextual."
            )

            st.divider()

            st.markdown(
                "## Liquidez"
            )

            exibir_cards_dashboard(
                cards_dashboard,
                [
                    "LG",
                    "LC",
                    "LS",
                    "ICJ",
                ],
                ano_base,
            )

            coluna_liquidez, coluna_icj = (
                st.columns(
                    [
                        2,
                        1,
                    ]
                )
            )

            with coluna_liquidez:

                exibir_grafico_dashboard(
                    graficos_dashboard[
                        "liquidez"
                    ],
                    key="grafico_liquidez_dashboard",
                )

            with coluna_icj:

                exibir_grafico_dashboard(
                    graficos_dashboard[
                        "icj"
                    ],
                    key="grafico_icj_dashboard",
                )

            st.caption(
                "LG, LC e LS são razões. "
                "O ICJ é apresentado separadamente "
                "por possuir escala própria em vezes."
            )

            st.divider()

            st.markdown(
                "## Lucratividade e Desempenho"
            )

            exibir_cards_dashboard(
                cards_dashboard,
                [
                    "GA",
                    "RSV",
                    "ROA",
                    "ROE",
                ],
                ano_base,
            )

            coluna_rentabilidade, coluna_ga = (
                st.columns(
                    [
                        2,
                        1,
                    ]
                )
            )

            with coluna_rentabilidade:

                exibir_grafico_dashboard(
                    graficos_dashboard[
                        "rentabilidade"
                    ],
                    key="grafico_rentabilidade_dashboard",
                )

            with coluna_ga:

                exibir_grafico_dashboard(
                    graficos_dashboard[
                        "ga"
                    ],
                    key="grafico_ga_dashboard",
                )

            st.caption(
                "RSV, ROA e ROE são percentuais. "
                "O Giro do Ativo é apresentado separadamente "
                "por utilizar unidade em vezes."
            )

            st.divider()
"""

    texto = substituir_unico(
        texto,
        antigo,
        novo,
        "Painel tradicional por layout",
    )

    antigo = """        if quadro_inds.empty:

            st.warning(
                "Indicadores não disponíveis."
            )

        else:

            for grupo in [
                "Estrutura de Capital",
                "Liquidez",
                "Lucratividade/Desempenho",
            ]:

                st.markdown(
                    f"### {grupo}"
                )

                tabela = (
                    tabela_indicadores_grupo(
                        quadro_inds,
                        grupo,
                        anos_desc,
                    )
                )

                st.dataframe(
                    tabela,
                    use_container_width=True,
                    hide_index=True,
                )


            st.divider()
"""

    novo = """        if quadro_inds.empty:

            st.warning(
                "Indicadores não disponíveis."
            )

        elif (
            "FINANCEIRA"
            in layouts_detectados
        ):
            st.markdown(
                "### Rentabilidade tradicional aplicável"
            )

            quadro_roa_roe = (
                quadro_inds.loc[
                    quadro_inds[
                        "INDICADOR"
                    ].isin(
                        [
                            "ROA",
                            "ROE",
                        ]
                    )
                ]
                .copy()
            )

            tabela_roa_roe = (
                tabela_indicadores_grupo(
                    quadro_roa_roe,
                    "Lucratividade/Desempenho",
                    anos_desc,
                )
            )

            st.dataframe(
                tabela_roa_roe,
                use_container_width=True,
                hide_index=True,
            )

            with st.expander(
                "Indicadores tradicionais não aplicáveis — auditoria metodológica"
            ):
                quadro_na = (
                    quadro_inds.loc[
                        quadro_inds[
                            "APLICABILIDADE"
                        ].eq(
                            "NAO_APLICAVEL"
                        )
                    ]
                    .copy()
                )

                for grupo_na in [
                    "Estrutura de Capital",
                    "Liquidez",
                    "Lucratividade/Desempenho",
                ]:
                    tabela_na = (
                        tabela_indicadores_grupo(
                            quadro_na,
                            grupo_na,
                            anos_desc,
                        )
                    )

                    if tabela_na.empty:
                        continue

                    st.markdown(
                        f"#### {grupo_na}"
                    )

                    st.dataframe(
                        tabela_na,
                        use_container_width=True,
                        hide_index=True,
                    )

            st.divider()

        else:

            for grupo in [
                "Estrutura de Capital",
                "Liquidez",
                "Lucratividade/Desempenho",
            ]:

                st.markdown(
                    f"### {grupo}"
                )

                tabela = (
                    tabela_indicadores_grupo(
                        quadro_inds,
                        grupo,
                        anos_desc,
                    )
                )

                st.dataframe(
                    tabela,
                    use_container_width=True,
                    hide_index=True,
                )


            st.divider()
"""

    texto = substituir_unico(
        texto,
        antigo,
        novo,
        "Tabela tradicional da aba Indicadores",
    )

    antigo = """                        options=(
                            ORDEM_INDICADORES
                        ),
"""

    novo = """                        options=(
                            [
                                "ROA",
                                "ROE",
                            ]
                            if (
                                "FINANCEIRA"
                                in layouts_detectados
                            )
                            else ORDEM_INDICADORES
                        ),
"""

    texto = substituir_unico(
        texto,
        antigo,
        novo,
        "Opções do detalhamento tradicional",
    )

    compile(
        texto,
        str(APP),
        "exec",
    )

    APP.write_text(
        texto,
        encoding="utf-8",
    )

    print()
    print("B.3 aplicada com sucesso.")
    print(f"app.py: {APP}")
    print(f"backup: {BACKUP}")
    print()
    print("Nenhuma fórmula foi alterada.")
    print("Nenhum arquivo de dados foi alterado.")
    print()
    print("Próximo comando:")
    print(
        r"python tests\test_integracao_financeira_b3.py"
    )


if __name__ == "__main__":
    main()

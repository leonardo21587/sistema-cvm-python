# Sistema CVM — Análise Financeira

Sistema acadêmico de análise financeira desenvolvido em Python e Streamlit a partir de Demonstrações Financeiras Padronizadas (DFP) consolidadas divulgadas pela CVM.

**Curso:** Ciências Econômicas — UFSJ  
**Acesso público:** https://indicadores-financeiros-cvm.streamlit.app

## Objetivo

Permitir a consulta de companhias do catálogo CVM e apresentar, de forma integrada:

- Balanço Patrimonial — Ativo;
- Balanço Patrimonial — Passivo;
- Demonstração do Resultado do Exercício;
- Análise Vertical (AV);
- Análise Horizontal (AH);
- 12 indicadores financeiros;
- decomposição DuPont;
- dashboard interativo;
- relatório automático de análise financeira;
- validações e auditoria;
- exportação completa para Excel.

## Período da versão atual

A versão atual utiliza como período principal:

- 2023;
- 2024;
- 2025.

Para indicadores que exigem saldo médio, o sistema utiliza 2022 como ano auxiliar quando aplicável.

## Apresentação das análises

- **VA — Valor Absoluto:** valores monetários em R$ mil, exibidos com duas casas decimais.
- **AV — Análise Vertical:** apresentada em percentual.
- **AH — Análise Horizontal:** índice de base fixa, com o primeiro exercício igual a 100%. Assim, por exemplo, `108,17%` significa que o valor corresponde a 108,17% do ano-base, ou crescimento de 8,17% em relação a ele.

A exportação para Excel segue a mesma lógica de apresentação usada no sistema web.

## Indicadores

### Estrutura de capital

- IPL — Imobilização do Patrimônio Líquido
- PCT — Participação de Capital de Terceiros
- CE — Composição do Endividamento
- EFSAT — Endividamento Financeiro sobre Ativo Total

### Liquidez

- LG — Liquidez Geral
- LC — Liquidez Corrente
- LS — Liquidez Seca
- ICJ — Índice de Cobertura de Juros

### Desempenho e rentabilidade

- GA — Giro do Ativo
- RSV — Retorno sobre Vendas
- ROA — Retorno sobre o Ativo
- ROE — Retorno sobre o Patrimônio Líquido

A decomposição DuPont utiliza:

`ROA = GA × RSV`

## Estrutura do sistema

```text
Sistema-CVM-Python/
├── app.py
├── README.md
├── requirements.txt
├── assets/
│   └── logo_ufsj.png
├── config/
├── src/
│   ├── banco.py
│   ├── demonstracoes.py
│   ├── padronizacao.py
│   ├── analise_vertical.py
│   ├── analise_horizontal.py
│   ├── indicadores.py
│   ├── validacao.py
│   ├── relatorio.py
│   ├── graficos.py
│   ├── exportacao.py
│   └── ano_auxiliar.py
├── tests/
│   └── auditoria_adversarial.py
└── data/
    └── processed/
        ├── dfp_2023_2025.parquet
        ├── empresas.parquet
        ├── saldos_auxiliares_2022.parquet
        └── sistema_cvm.duckdb
```

## Auditoria

Antes da publicação, a versão foi submetida a uma auditoria adversarial automatizada.

Resultado da varredura completa:

- 499 companhias analisadas;
- 6.083 testes aprovados;
- 499 registros informativos;
- 0 falhas técnicas.

A auditoria incluiu situações como:

- patrimônio líquido negativo;
- prejuízo;
- denominadores iguais a zero;
- ativo e receita iguais a zero;
- mudança de sinal de resultados;
- mudança de sinal do patrimônio líquido;
- períodos incompletos;
- empresas em recuperação judicial;
- empresas em liquidação;
- validação da identidade DuPont;
- geração do relatório;
- geração do arquivo Excel.

## Execução local

Recomenda-se Python 3.12.

Instale as dependências:

```bash
pip install -r requirements.txt
```

Depois execute:

```bash
python -m streamlit run app.py
```

## Uso

1. Pesquise a companhia por nome, código CVM ou CNPJ.
2. Selecione a empresa desejada.
3. Consulte as demonstrações, indicadores, dashboard e relatório.
4. Utilize a aba de metodologia/auditoria para verificar os controles de integridade.
5. Exporte a análise para Excel quando necessário.

## Fonte dos dados

Os dados financeiros são derivados das Demonstrações Financeiras Padronizadas (DFP) consolidadas disponibilizadas pela Comissão de Valores Mobiliários (CVM).

## Observações metodológicas

O sistema preserva valores ausentes como `N/D` e evita divisões por zero. Alertas e bloqueios de validação são tratados separadamente de interpretações financeiras.

O relatório automático utiliza regras determinísticas. Ele não atribui uma nota global de “saúde financeira” e não substitui julgamento profissional ou análise contextual da companhia.

## Natureza do projeto

Projeto acadêmico desenvolvido para a disciplina de Administração Financeira no curso de Ciências Econômicas da UFSJ.

A identificação visual da UFSJ é utilizada no contexto acadêmico do projeto. Este repositório não constitui página institucional da Universidade.

Não constitui recomendação de investimento.

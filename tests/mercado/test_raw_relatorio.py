from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mercado.arquivos import (  # noqa: E402
    calcular_sha256,
    preservar_arquivo_raw,
)
from src.mercado.relatorio_ingestao import (  # noqa: E402
    novo_relatorio_ingestao,
    salvar_relatorio_ingestao,
)


def teste_raw_idempotente():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        origem = raiz / "COTAHIST_A2025.ZIP"
        origem.write_bytes(b"conteudo-b3-fixture")

        raw_root = raiz / "raw"

        a = preservar_arquivo_raw(
            origem,
            fonte="b3",
            ano=2025,
            raiz_raw=raw_root,
            coletado_em="2026-09-19T07:00:00+00:00",
        )
        b = preservar_arquivo_raw(
            origem,
            fonte="b3",
            ano=2025,
            raiz_raw=raw_root,
            coletado_em="2026-09-19T08:00:00+00:00",
        )

        assert a.sha256 == calcular_sha256(origem)
        assert b.sha256 == a.sha256
        assert b.primeira_coleta_em == "2026-09-19T07:00:00+00:00"
        assert b.ultima_coleta_em == "2026-09-19T08:00:00+00:00"

        manifesto = (
            raw_root
            / "b3"
            / "cotahist"
            / "2025"
            / "manifesto.json"
        )
        registros = json.loads(manifesto.read_text(encoding="utf-8"))
        assert len(registros) == 1


def teste_mesmo_nome_com_conteudo_diferente_preserva_ambos():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        origem = raiz / "COTAHIST_A2025.ZIP"
        raw_root = raiz / "raw"

        origem.write_bytes(b"versao-1")
        primeiro = preservar_arquivo_raw(
            origem,
            fonte="b3",
            ano=2025,
            raiz_raw=raw_root,
            coletado_em="2026-09-19T07:00:00+00:00",
        )

        origem.write_bytes(b"versao-2")
        segundo = preservar_arquivo_raw(
            origem,
            fonte="b3",
            ano=2025,
            raiz_raw=raw_root,
            coletado_em="2026-09-20T07:00:00+00:00",
        )

        assert primeiro.sha256 != segundo.sha256
        assert primeiro.nome_armazenado == "COTAHIST_A2025.ZIP"
        assert segundo.nome_armazenado.startswith(
            "COTAHIST_A2025__"
        )

        destino_dir = raw_root / "b3" / "cotahist" / "2025"
        arquivos_zip = sorted(destino_dir.glob("*.ZIP"))
        assert len(arquivos_zip) == 2


def teste_relatorio_ingestao():
    with tempfile.TemporaryDirectory() as tmp:
        relatorio = novo_relatorio_ingestao(
            fonte="B3_COTAHIST",
            ano=2025,
            arquivo_fonte="COTAHIST_A2025.ZIP",
            sha256_raw="abc123",
            iniciado_em="2026-09-19T07:00:00+00:00",
        )

        relatorio.linhas_brutas = 100
        relatorio.linhas_cotacao = 98
        relatorio.linhas_fora_escopo = 60
        relatorio.linhas_elegiveis = 38
        relatorio.linhas_mapeadas = 37
        relatorio.linhas_sem_instrumento = 1

        relatorio.registrar_persistencia("INSERIDO")
        relatorio.registrar_persistencia("IGUAL")
        relatorio.registrar_persistencia("ATUALIZADO")

        relatorio.descontinuidades_sinalizadas = 2
        relatorio.falhas_invariantes = 0

        relatorio.finalizar(
            status="APROVADO",
            finalizado_em="2026-09-19T07:30:00+00:00",
        )

        caminho_json, caminho_csv = salvar_relatorio_ingestao(
            relatorio,
            diretorio=Path(tmp) / "reports",
        )

        dados = json.loads(caminho_json.read_text(encoding="utf-8"))

        assert dados["inseridos"] == 1
        assert dados["iguais"] == 1
        assert dados["atualizados"] == 1
        assert dados["substituicoes"] == 1
        assert dados["status"] == "APROVADO"

        linhas_csv = caminho_csv.read_text(
            encoding="utf-8-sig"
        ).splitlines()
        assert len(linhas_csv) == 2


def main():
    print("=" * 72)
    print("SISTEMA CVM — TESTE D.3 — RAW E RELATÓRIO DE INGESTÃO")
    print("=" * 72)

    teste_raw_idempotente()
    teste_mesmo_nome_com_conteudo_diferente_preserva_ambos()
    teste_relatorio_ingestao()

    print("RESULTADO: APROVADO")
    print("raw imutável + SHA-256: aprovado")
    print("replay raw idempotente: aprovado")
    print("revisão de mesmo nome preservada: aprovado")
    print("relatório JSON + CSV-resumo: aprovado")


if __name__ == "__main__":
    main()

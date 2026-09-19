from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RelatorioIngestao:
    fonte: str
    ano: int
    arquivo_fonte: str
    sha256_raw: str
    iniciado_em: str
    finalizado_em: str | None = None

    linhas_brutas: int = 0
    linhas_cotacao: int = 0
    linhas_fora_escopo: int = 0
    linhas_elegiveis: int = 0
    linhas_mapeadas: int = 0
    linhas_sem_instrumento: int = 0

    inseridos: int = 0
    iguais: int = 0
    atualizados: int = 0
    substituicoes: int = 0

    descontinuidades_sinalizadas: int = 0
    falhas_invariantes: int = 0

    status: str = "EM_ANDAMENTO"
    observacoes: str = ""

    def finalizar(
        self,
        *,
        status: str,
        observacoes: str = "",
        finalizado_em: str | None = None,
    ) -> None:
        self.status = str(status).strip().upper()
        self.observacoes = str(observacoes)
        self.finalizado_em = finalizado_em or _agora_iso_utc()

    def registrar_persistencia(self, resultado: str) -> None:
        resultado = str(resultado).strip().upper()

        if resultado == "INSERIDO":
            self.inseridos += 1
        elif resultado == "IGUAL":
            self.iguais += 1
        elif resultado == "ATUALIZADO":
            self.atualizados += 1
            self.substituicoes += 1
        else:
            raise ValueError(
                f"Resultado de persistência desconhecido: {resultado!r}"
            )


def _agora_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def novo_relatorio_ingestao(
    *,
    fonte: str,
    ano: int,
    arquivo_fonte: str,
    sha256_raw: str,
    iniciado_em: str | None = None,
) -> RelatorioIngestao:
    return RelatorioIngestao(
        fonte=str(fonte).strip().upper(),
        ano=int(ano),
        arquivo_fonte=str(arquivo_fonte),
        sha256_raw=str(sha256_raw).lower(),
        iniciado_em=iniciado_em or _agora_iso_utc(),
    )


def salvar_relatorio_ingestao(
    relatorio: RelatorioIngestao,
    *,
    diretorio: str | Path,
) -> tuple[Path, Path]:
    """
    Salva um JSON detalhado e acrescenta uma linha ao CSV-resumo.

    A gravação JSON usa arquivo temporário + replace para evitar relatório
    parcialmente escrito em caso de interrupção.
    """
    diretorio = Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)

    if relatorio.finalizado_em is None:
        raise RuntimeError(
            "Relatório precisa ser finalizado antes de ser persistido."
        )

    dados = asdict(relatorio)

    carimbo = (
        relatorio.finalizado_em
        .replace(":", "")
        .replace("-", "")
        .replace("+", "_")
        .replace(".", "_")
    )
    nome_base = (
        f"ingestao_{relatorio.fonte.lower()}_{relatorio.ano}_{carimbo}"
    )

    caminho_json = diretorio / f"{nome_base}.json"
    temporario = caminho_json.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(
            dados,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    temporario.replace(caminho_json)

    caminho_csv = diretorio / "resumo_ingestoes.csv"
    existe = caminho_csv.exists()

    with caminho_csv.open(
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=list(dados.keys()),
            delimiter=";",
        )
        if not existe:
            escritor.writeheader()
        escritor.writerow(dados)

    return caminho_json, caminho_csv

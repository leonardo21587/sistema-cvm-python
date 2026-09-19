from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
MARKET_DIR = ROOT_DIR / "data" / "market"
RAW_DIR = MARKET_DIR / "raw"
REPORTS_DIR = MARKET_DIR / "reports"


@dataclass(frozen=True)
class ArquivoRaw:
    fonte: str
    ano: int
    nome_original: str
    nome_armazenado: str
    caminho_relativo: str
    sha256: str
    tamanho_bytes: int
    primeira_coleta_em: str
    ultima_coleta_em: str


def _agora_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def calcular_sha256(caminho: str | Path) -> str:
    caminho = Path(caminho)
    digest = hashlib.sha256()

    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)

    return digest.hexdigest()


def _ler_manifesto(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []

    conteudo = json.loads(caminho.read_text(encoding="utf-8"))

    if not isinstance(conteudo, list):
        raise RuntimeError(
            f"Manifesto raw inválido: esperado lista em {caminho}"
        )

    return conteudo


def _salvar_manifesto(caminho: Path, registros: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)

    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(
            registros,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    temporario.replace(caminho)


def preservar_arquivo_raw(
    caminho_origem: str | Path,
    *,
    fonte: str,
    ano: int,
    raiz_raw: str | Path | None = None,
    coletado_em: str | None = None,
) -> ArquivoRaw:
    """
    Preserva um arquivo bruto de forma imutável e rastreável.

    Regras:
    - conteúdo idêntico não é duplicado;
    - mesmo nome com conteúdo diferente é preservado com sufixo de hash;
    - o manifesto registra SHA-256, tamanho e primeira/última coleta;
    - nenhuma transformação é aplicada aos bytes de origem.
    """
    origem = Path(caminho_origem)

    if not origem.is_file():
        raise FileNotFoundError(f"Arquivo raw não encontrado: {origem}")

    fonte_normalizada = str(fonte).strip().lower()
    if not fonte_normalizada:
        raise ValueError("FONTE não pode ser vazia.")

    ano = int(ano)
    instante = coletado_em or _agora_iso_utc()

    raiz = Path(raiz_raw) if raiz_raw is not None else RAW_DIR
    destino_dir = raiz / fonte_normalizada / "cotahist" / str(ano)
    destino_dir.mkdir(parents=True, exist_ok=True)

    manifesto = destino_dir / "manifesto.json"
    registros = _ler_manifesto(manifesto)

    sha = calcular_sha256(origem)
    tamanho = origem.stat().st_size

    for indice, registro in enumerate(registros):
        if registro.get("sha256") == sha:
            registro = dict(registro)
            registro["ultima_coleta_em"] = instante
            registros[indice] = registro
            _salvar_manifesto(manifesto, registros)
            return ArquivoRaw(**registro)

    nome = origem.name
    destino = destino_dir / nome

    if destino.exists():
        hash_existente = calcular_sha256(destino)
        if hash_existente != sha:
            destino = destino_dir / (
                f"{origem.stem}__{sha[:12]}{origem.suffix}"
            )

    if not destino.exists():
        shutil.copyfile(origem, destino)

    relativo = destino.relative_to(raiz).as_posix()

    item = ArquivoRaw(
        fonte=fonte_normalizada.upper(),
        ano=ano,
        nome_original=origem.name,
        nome_armazenado=destino.name,
        caminho_relativo=relativo,
        sha256=sha,
        tamanho_bytes=tamanho,
        primeira_coleta_em=instante,
        ultima_coleta_em=instante,
    )

    registros.append(asdict(item))
    registros.sort(
        key=lambda x: (
            int(x["ano"]),
            str(x["nome_armazenado"]),
            str(x["sha256"]),
        )
    )
    _salvar_manifesto(manifesto, registros)

    return item

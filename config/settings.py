from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"

ANOS_ANALISE = (2023, 2024, 2025)

DEMONSTRACOES = ("BPA", "BPP", "DRE")

CVM_DFP_BASE_URL = (
    "https://dados.cvm.gov.br/dados/"
    "CIA_ABERTA/DOC/DFP/DADOS"
)

REQUEST_TIMEOUT = 180
CHUNK_SIZE = 1024 * 1024

for pasta in (RAW_DIR, PROCESSED_DIR, EXPORTS_DIR):
    pasta.mkdir(parents=True, exist_ok=True)

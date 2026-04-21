import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8008").rstrip("/")
VLLM_CHAT_URL = f"{VLLM_BASE_URL}/v1/chat/completions"
VLLM_MODELS_URL = f"{VLLM_BASE_URL}/v1/models"
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen3.6-35B-A3B")

TUNNEL_HEADERS = {
    "bypass-tunnel-reminder": "true",
    "User-Agent": "OCR-HVKS-Client/1.0",
}

OCR_PORT = int(os.environ.get("OCR_PORT", 8900))
LATEX_PORT = int(os.environ.get("LATEX_PORT", 8901))

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", 32))
DPI = int(os.environ.get("DPI", 300))

DEBUG_DIR = Path(os.environ.get("DEBUG_DIR", "./debug_latex"))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

POPPLER_PATH = os.environ.get("POPPLER_PATH") or None

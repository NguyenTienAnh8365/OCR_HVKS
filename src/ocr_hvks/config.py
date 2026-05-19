"""Cấu hình toàn cục — load từ env / .env ở repo root."""

import os
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


# ---------- LLM (vLLM OpenAI-compatible) ----------
LLM_BASE_URL = os.environ.get(
    "LLM_BASE_URL",
    os.environ.get("VLLM_BASE_URL", "http://localhost:8008"),
).rstrip("/")
LLM_CHAT_URL = f"{LLM_BASE_URL}/v1/chat/completions"
LLM_MODELS_URL = f"{LLM_BASE_URL}/v1/models"
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen3.6-35B-A3B")

# Headers gửi kèm khi LLM nằm sau cloudflared/localtunnel.
TUNNEL_HEADERS = {
    "bypass-tunnel-reminder": "true",
    "User-Agent": "OCR-HVKS-Client/3.0",
}


# ---------- API server ----------
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", 8900))


# ---------- OCR ----------
# Trần số trang OCR gọi vLLM ĐỒNG THỜI trên toàn app (mọi request cộng lại).
# Nên xấp xỉ MAX_NUM_SEQS của vLLM: đủ để nạp full tải mà không flood backend.
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", 512))
DPI = int(os.environ.get("DPI", 300))
POPPLER_PATH = os.environ.get("POPPLER_PATH") or None


# ---------- LaTeX ----------
LATEX_CHUNK_WORKERS = int(os.environ.get("LATEX_CHUNK_WORKERS", 4))
LATEX_PAGES_PER_CHUNK = int(os.environ.get("LATEX_PAGES_PER_CHUNK", 4))


# ---------- Debug ----------
DEBUG_DIR = Path(os.environ.get("DEBUG_DIR", str(REPO_ROOT / "debug" / "latex")))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

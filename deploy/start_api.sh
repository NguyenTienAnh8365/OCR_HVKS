#!/usr/bin/env bash
# Khởi động FastAPI combined server (OCR + Extract + LaTeX) với uvicorn.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a; . "${ENV_FILE}"; set +a
fi

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8900}"
WORKERS="${API_WORKERS:-1}"
LOG_LEVEL="${API_LOG_LEVEL:-info}"

export PYTHONPATH="${REPO_ROOT}/src:${PYTHONPATH:-}"

echo "[api] host=${API_HOST} port=${API_PORT} workers=${WORKERS}"
exec uvicorn ocr_hvks.api.app:app \
  --host "${API_HOST}" \
  --port "${API_PORT}" \
  --workers "${WORKERS}" \
  --log-level "${LOG_LEVEL}"

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

# Trần số request đồng thời event loop ôm; vượt → uvicorn trả 503. Đặt rộng
# (backpressure thật nằm ở LLM_CONCURRENCY) — đây chỉ là chốt chặn runaway.
LIMIT_CONCURRENCY="${API_LIMIT_CONCURRENCY:-1024}"
# Khi restart: chờ tối đa ngần này giây cho request đang chạy xong trước khi
# cắt — tránh đứt ngang job sắp hoàn tất.
GRACEFUL="${API_TIMEOUT_GRACEFUL:-30}"

export PYTHONPATH="${REPO_ROOT}/src:${PYTHONPATH:-}"

echo "[api] host=${API_HOST} port=${API_PORT} workers=${WORKERS}"
echo "[api] limit_concurrency=${LIMIT_CONCURRENCY} graceful=${GRACEFUL}s"
# --proxy-headers + --forwarded-allow-ips: lấy IP client thật khi đứng sau
# cloudflared, để log request có IP đúng.
exec uvicorn ocr_hvks.api.app:app \
  --host "${API_HOST}" \
  --port "${API_PORT}" \
  --workers "${WORKERS}" \
  --log-level "${LOG_LEVEL}" \
  --limit-concurrency "${LIMIT_CONCURRENCY}" \
  --timeout-graceful-shutdown "${GRACEFUL}" \
  --proxy-headers \
  --forwarded-allow-ips '*'

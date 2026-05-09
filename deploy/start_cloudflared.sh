#!/usr/bin/env bash
# Mở quick-tunnel cloudflared trỏ tới FastAPI (mặc định port 8900).
# In ra https URL trên trycloudflare.com để paste vào ocr_v3.html?api=...

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a; . "${ENV_FILE}"; set +a
fi

API_PORT="${API_PORT:-8900}"
LOG_FILE="${REPO_ROOT}/cloudflared.log"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "ERROR: cloudflared chưa cài. Chạy deploy/install_server.sh hoặc:"
  echo "  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared"
  echo "  chmod +x /usr/local/bin/cloudflared"
  exit 1
fi

echo "[cloudflared] tunneling http://localhost:${API_PORT} (log: ${LOG_FILE})"
exec cloudflared tunnel --url "http://localhost:${API_PORT}" --no-autoupdate 2>&1 | tee "${LOG_FILE}"

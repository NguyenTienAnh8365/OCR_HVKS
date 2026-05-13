#!/usr/bin/env bash
# Khởi động SGLang server (OpenAI-compatible) phục vụ Qwen3.6-35B-A3B.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a; . "${ENV_FILE}"; set +a
fi

MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3.6-35B-A3B}"
SGLANG_PORT="${SGLANG_PORT:-8008}"
SGLANG_HOST="${SGLANG_HOST:-0.0.0.0}"
TP_SIZE="${TP_SIZE:-2}"
MEM_FRACTION_STATIC="${MEM_FRACTION_STATIC:-0.90}"
CONTEXT_LENGTH="${CONTEXT_LENGTH:-32768}"
MAX_RUNNING_REQUESTS="${MAX_RUNNING_REQUESTS:-64}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8_e5m2}"
DTYPE="${DTYPE:-bfloat16}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-16384}"
CHAT_TEMPLATE="${CHAT_TEMPLATE:-qwen2-vl}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
export HF_HOME="${HF_HOME:-$HOME/model/qwen3.6-35B-A3B}"

echo "[sglang] model=${MODEL_NAME} tp=${TP_SIZE} port=${SGLANG_PORT} ctx=${CONTEXT_LENGTH}"
echo "[sglang] gpus=${CUDA_VISIBLE_DEVICES} mem_frac=${MEM_FRACTION_STATIC} kv_cache=${KV_CACHE_DTYPE}"

exec python -m sglang.launch_server \
  --model-path "${MODEL_NAME}" \
  --host "${SGLANG_HOST}" \
  --port "${SGLANG_PORT}" \
  --tp-size "${TP_SIZE}" \
  --mem-fraction-static "${MEM_FRACTION_STATIC}" \
  --context-length "${CONTEXT_LENGTH}" \
  --max-running-requests "${MAX_RUNNING_REQUESTS}" \
  --kv-cache-dtype "${KV_CACHE_DTYPE}" \
  --dtype "${DTYPE}" \
  --chunked-prefill-size "${MAX_NUM_BATCHED_TOKENS}" \
  --chat-template "${CHAT_TEMPLATE}" \
  --attention-backend triton \
  --enable-mixed-chunk \
  --enable-torch-compile \
  --schedule-conservativeness 1.3\
  --trust-remote-code

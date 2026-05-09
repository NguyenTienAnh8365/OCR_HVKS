#!/usr/bin/env bash
# Khởi động SGLang server (OpenAI-compatible) phục vụ Qwen3.
#
# Mặc định:
#   - 2x RTX PRO 6000 Blackwell (~96GB) → TP=2.
#   - flashinfer attention backend (tối ưu cho Blackwell sm_120).
#   - radix cache + chunked prefill bật mặc định trong SGLang, không cần flag riêng.
#   - chat template auto-detect từ tokenizer_config.json (Qwen3 đã embed sẵn).
#
# Override qua biến môi trường hoặc .env, ví dụ:
#   MODEL_NAME=Qwen/Qwen3-32B TP_SIZE=2 ./deploy/start_sglang.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a; . "${ENV_FILE}"; set +a
fi

# ---------- Model ----------
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3.6-27B}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-${MODEL_NAME}}"

# ---------- Listen ----------
SGLANG_HOST="${SGLANG_HOST:-0.0.0.0}"
SGLANG_PORT="${SGLANG_PORT:-8008}"

# ---------- Parallelism ----------
# TP=2 dùng cả 2 GPU. Nếu đặt TP=1 thì set CUDA_VISIBLE_DEVICES=0 để khỏi phí GPU thứ 2.
TP_SIZE="${TP_SIZE:-2}"
DP_SIZE="${DP_SIZE:-1}"

# ---------- Memory & cache ----------
MEM_FRACTION_STATIC="${MEM_FRACTION_STATIC:-0.88}"
CONTEXT_LENGTH="${CONTEXT_LENGTH:-100000}"
MAX_RUNNING_REQUESTS="${MAX_RUNNING_REQUESTS:-64}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8_e5m2}"
DTYPE="${DTYPE:-bfloat16}"

# ---------- Throughput ----------
CHUNKED_PREFILL_SIZE="${CHUNKED_PREFILL_SIZE:-16384}"
SCHEDULE_CONSERVATIVENESS="${SCHEDULE_CONSERVATIVENESS:-1.0}"

# ---------- Backend ----------
# triton | trtllm_mha | flashinfer | fa3 | torch_native
# Lưu ý: Qwen3-Next / hybrid GDN models trên Blackwell BẮT BUỘC triton hoặc trtllm_mha.
ATTENTION_BACKEND="${ATTENTION_BACKEND:-triton}"

# Reasoning parser cho Qwen3 — tách <think>…</think> nếu model emit. Để rỗng để tắt.
REASONING_PARSER="${REASONING_PARSER:-qwen3}"

# ---------- Env ----------
LOG_LEVEL="${SGLANG_LOG_LEVEL:-info}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
export HF_HOME="${HF_HOME:-$HOME/model/qwen3.6}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"

echo "[sglang] model=${MODEL_NAME} served_as=${SERVED_MODEL_NAME}"
echo "[sglang] gpus=${CUDA_VISIBLE_DEVICES} tp=${TP_SIZE} dp=${DP_SIZE} attn=${ATTENTION_BACKEND}"
echo "[sglang] ctx=${CONTEXT_LENGTH} mem_frac=${MEM_FRACTION_STATIC} kv=${KV_CACHE_DTYPE} dtype=${DTYPE}"
echo "[sglang] chunked_prefill=${CHUNKED_PREFILL_SIZE} max_running=${MAX_RUNNING_REQUESTS}"
echo "[sglang] HF_HOME=${HF_HOME}"

ARGS=(
  --model-path "${MODEL_NAME}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --host "${SGLANG_HOST}"
  --port "${SGLANG_PORT}"
  --tp-size "${TP_SIZE}"
  --dp-size "${DP_SIZE}"
  --mem-fraction-static "${MEM_FRACTION_STATIC}"
  --context-length "${CONTEXT_LENGTH}"
  --max-running-requests "${MAX_RUNNING_REQUESTS}"
  --kv-cache-dtype "${KV_CACHE_DTYPE}"
  --dtype "${DTYPE}"
  --chunked-prefill-size "${CHUNKED_PREFILL_SIZE}"
  --schedule-conservativeness "${SCHEDULE_CONSERVATIVENESS}"
  --attention-backend "${ATTENTION_BACKEND}"
  --log-level "${LOG_LEVEL}"
  --trust-remote-code
)

if [[ -n "${REASONING_PARSER}" ]]; then
  ARGS+=(--reasoning-parser "${REASONING_PARSER}")
fi

exec python -m sglang.launch_server "${ARGS[@]}"

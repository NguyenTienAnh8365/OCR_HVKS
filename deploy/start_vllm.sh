#!/usr/bin/env bash
# Khởi động vLLM server (OpenAI-compatible) phục vụ Qwen3.6-35B-A3B (MoE).
#
# Mặc định cho 2x RTX PRO 6000 Blackwell (~96GB) → TP=2.
# Override qua biến môi trường hoặc .env.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a; . "${ENV_FILE}"; set +a
fi

MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3.6-35B-A3B}"

VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8008}"

TP_SIZE="${TP_SIZE:-2}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-32}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-32768}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8_e5m2}"
DTYPE="${DTYPE:-bfloat16}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
export HF_HOME="${HF_HOME:-$HOME/model/qwen3.6-35B-A3B}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"

echo "[vllm] model=${MODEL_NAME} tp=${TP_SIZE} port=${VLLM_PORT}"
echo "[vllm] gpus=${CUDA_VISIBLE_DEVICES} gpu_mem=${GPU_MEMORY_UTILIZATION} ctx=${MAX_MODEL_LEN}"
echo "[vllm] max_num_seqs=${MAX_NUM_SEQS} max_num_batched_tokens=${MAX_NUM_BATCHED_TOKENS}"
echo "[vllm] HF_HOME=${HF_HOME}"

exec vllm serve "${MODEL_NAME}" \
  --host "${VLLM_HOST}" \
  --port "${VLLM_PORT}" \
  --tensor-parallel-size "${TP_SIZE}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}" \
  --kv-cache-dtype "${KV_CACHE_DTYPE}" \
  --dtype "${DTYPE}" \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --trust-remote-code

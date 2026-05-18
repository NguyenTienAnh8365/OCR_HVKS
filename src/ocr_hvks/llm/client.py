"""Wrapper gọi LLM qua HTTP OpenAI-compatible.

Backend expose `/v1/chat/completions` và `/v1/models` theo OpenAI-compatible API,
nên client này không phụ thuộc engine cụ thể, chỉ cần đổi `LLM_BASE_URL`.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ocr_hvks.config import (
    LLM_CHAT_URL,
    LLM_MODELS_URL,
    MAX_WORKERS,
    MODEL_NAME,
    TUNNEL_HEADERS,
)


# Shared session với connection pool đủ lớn để cover MAX_WORKERS concurrent calls.
# Không có session: mỗi requests.post mở TCP mới → 256 socket tear-down/sec
# gây TIME_WAIT pile-up + tail latency cao. Session + keep-alive tái dùng TCP.
#
# Cạm bẫy: uvicorn của vLLM đóng kết nối keep-alive idle sau ~5s. Trong lúc
# poppler render chunk kế tiếp, kết nối trong pool nằm idle → bị server đóng.
# Nếu để max_retries=0, lần dùng lại kết nối chết đó ném ConnectionError và
# vòng retry ở ocr_one_page phạt sleep(1.5s+) → throughput tụt.
#
# Retry dưới đây cho urllib3 TỰ thay kết nối chết ngay trong một lần gọi:
# backoff_factor=0 nên không sleep, allowed_methods=False để retry cả POST
# (mặc định urllib3 bỏ qua POST). Kết nối chết chỉ còn tốn 1 round-trip.
_retry = Retry(
    total=3,
    connect=3,
    read=2,
    status=0,
    backoff_factor=0,        # thay kết nối ngay, không chờ
    allowed_methods=False,   # False = retry mọi method, kể cả POST
    raise_on_status=False,
)
_session = requests.Session()
_pool_size = max(MAX_WORKERS, 128)
_adapter = HTTPAdapter(
    pool_connections=_pool_size,
    pool_maxsize=_pool_size,
    max_retries=_retry,
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def list_models():
    r = _session.get(LLM_MODELS_URL, headers=TUNNEL_HEADERS, timeout=10)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


def chat(messages, *, max_tokens=4096, temperature=0.0, stream=False,
         extra: dict | None = None, timeout=600):
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if extra:
        payload.update(extra)
    return _session.post(
        LLM_CHAT_URL,
        json=payload,
        headers=TUNNEL_HEADERS,
        timeout=timeout,
        stream=stream,
    )

"""Wrapper gọi LLM qua HTTP OpenAI-compatible.

Backend expose `/v1/chat/completions` và `/v1/models` theo OpenAI-compatible API,
nên client này không phụ thuộc engine cụ thể, chỉ cần đổi `LLM_BASE_URL`.
"""

import requests

from ocr_hvks.config import (
    LLM_CHAT_URL,
    LLM_MODELS_URL,
    MODEL_NAME,
    TUNNEL_HEADERS,
)


def list_models():
    r = requests.get(LLM_MODELS_URL, headers=TUNNEL_HEADERS, timeout=10)
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
    return requests.post(
        LLM_CHAT_URL,
        json=payload,
        headers=TUNNEL_HEADERS,
        timeout=timeout,
        stream=stream,
    )

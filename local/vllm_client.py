import requests
from config import VLLM_CHAT_URL, VLLM_MODELS_URL, MODEL_NAME, TUNNEL_HEADERS


def check_vllm():
    r = requests.get(VLLM_MODELS_URL, headers=TUNNEL_HEADERS, timeout=10)
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
        VLLM_CHAT_URL,
        json=payload,
        headers=TUNNEL_HEADERS,
        timeout=timeout,
        stream=stream,
    )

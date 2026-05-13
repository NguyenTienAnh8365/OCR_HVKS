"""OCR pipeline: encode ảnh → gọi LLM Qwen-VL → clean output."""

import base64
import re
import time
from io import BytesIO

from PIL import Image

from ocr_hvks.llm import client as llm_client
from ocr_hvks.ocr.prompts import build_ocr_prompt


_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:markdown|md|text)?\s*[\r\n]+|[\r\n]+\s*```\s*$",
    re.IGNORECASE,
)


def encode_pil(img: Image.Image, max_side: int = 1568) -> str:
    """Encode PIL → base64 JPEG. Cap max(W, H) ≤ max_side để giảm visual tokens.

    Qwen-VL patch grid native ~1568 px; vượt ngưỡng này model tự down-sample,
    nên resize trước tiết kiệm bytes truyền + visual tokens prefill.
    """
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def clean_output(text: str) -> str:
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?thinking>", "", text, flags=re.IGNORECASE).strip()
    text = _CODE_FENCE_RE.sub("", text).strip()
    return text


def _build_page_result(page_num: int, value: str, elapsed: float, ok: bool) -> dict:
    return {
        "page": page_num,
        "text": value,
        "format": "text",
        "time_s": round(elapsed, 2),
        "ok": ok,
    }


def ocr_one_page(b64: str, page_num: int, total: int, fname: str) -> dict:
    started_at = time.time()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": build_ocr_prompt(fname, page_num, total)},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ],
    }]

    last_err = "unknown"
    for attempt in range(3):
        try:
            response = llm_client.chat(
                messages,
                max_tokens=6000,
                temperature=0.05,
                extra={
                    "top_p": 0.8,
                    # "repetition_penalty": 1.03,
                    "frequency_penalty": 0.0,
                },
                timeout=300,
            )
            if response.status_code != 200:
                last_err = f"HTTP {response.status_code}: {response.text[:200]}"
            else:
                try:
                    payload = response.json()
                except Exception as exc:
                    last_err = f"JSON decode: {exc} | body[:200]={response.text[:200]!r}"
                else:
                    if "choices" in payload:
                        text = clean_output(payload["choices"][0]["message"]["content"])
                        return _build_page_result(page_num, text, time.time() - started_at, True)
                    last_err = f"no choices: {str(payload)[:200]}"
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"

        time.sleep(1.5 * (attempt + 1))

    return _build_page_result(page_num, last_err, time.time() - started_at, False)

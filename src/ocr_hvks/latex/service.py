"""Sinh LaTeX body từ OCR text (chunked + song song) và repair khi compile fail."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import HTTPException

from ocr_hvks.config import LATEX_CHUNK_WORKERS, LATEX_PAGES_PER_CHUNK
from ocr_hvks.llm import client as llm_client
from ocr_hvks.latex.normalize import (
    normalize_ocr_input,
    split_ocr_by_page,
    strip_wrapping,
)
from ocr_hvks.latex.prompts import SYSTEM_PROMPT, build_latex_request


def call_llm(user_text: str, *, stream: bool = False, max_tokens: int = 16384,
             is_continuation: bool = False):
    normalized_input = normalize_ocr_input(user_text)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_latex_request(normalized_input, is_continuation=is_continuation)},
    ]
    return llm_client.chat(
        messages,
        max_tokens=max_tokens,
        temperature=0.0,
        stream=stream,
        extra={"top_p": 1.0},
        timeout=600,
    )


def generate_latex_body_single(user_text: str, *, max_tokens: int = 16384,
                               retries: int = 2, is_continuation: bool = False):
    last_status = None
    last_detail = "unknown"
    last_raw = ""
    last_body = ""

    for attempt in range(retries + 1):
        try:
            r = call_llm(user_text, stream=False, max_tokens=max_tokens,
                         is_continuation=is_continuation)
            last_status = r.status_code
            if r.status_code != 200:
                last_detail = f"LLM error {r.status_code}: {r.text[:500]}"
            else:
                data = r.json()
                choice = data["choices"][0]
                last_raw = choice["message"]["content"] or ""
                finish_reason = choice.get("finish_reason", "")
                last_body = strip_wrapping(last_raw)
                if finish_reason == "length":
                    print(f"[WARN] attempt={attempt} finish_reason=length — output bị cắt do max_tokens={max_tokens}. raw_len={len(last_raw)}")
                if last_body.strip() and finish_reason != "length":
                    return last_raw, last_body
                if finish_reason == "length" and attempt == retries:
                    last_detail = f"Output bị cắt (finish_reason=length, max_tokens={max_tokens}). raw_len={len(last_raw)}"
                elif not last_body.strip():
                    last_detail = f"LLM trả về rỗng sau khi strip. raw_head={last_raw[:400]!r}"
        except Exception as e:
            last_detail = f"{type(e).__name__}: {e}"

        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    status_code = 422 if last_status == 200 else 502
    raise HTTPException(status_code=status_code, detail=last_detail)


def generate_latex_body(user_text: str, *, max_tokens: int = 16384, retries: int = 2,
                        max_workers: int = LATEX_CHUNK_WORKERS):
    """Split OCR input per page and generate LaTeX in parallel. 1 page = 1 request."""
    chunks = split_ocr_by_page(user_text, LATEX_PAGES_PER_CHUNK)
    if not chunks:
        raise HTTPException(400, "text rỗng sau khi tách trang")

    if len(chunks) == 1:
        return generate_latex_body_single(
            chunks[0][0], max_tokens=max_tokens, retries=retries, is_continuation=False
        )

    print(
        f"[latex] chunks={len(chunks)} · workers={max_workers} · "
        f"pages_per_chunk={LATEX_PAGES_PER_CHUNK} · groups={[p for _, p in chunks]}",
        flush=True,
    )

    raws = [None] * len(chunks)
    bodies = [None] * len(chunks)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(chunks))) as pool:
        fut_to_idx = {
            pool.submit(
                generate_latex_body_single,
                chunk_text,
                max_tokens=max_tokens,
                retries=retries,
                is_continuation=(i > 0),
            ): i
            for i, (chunk_text, _pnums) in enumerate(chunks)
        }
        for fut in as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            raw, body = fut.result()
            raws[idx] = raw
            bodies[idx] = body

    raw_joined = "\n\n%%%%% PAGE %%%%%\n\n".join(r or "" for r in raws)
    body_joined = "\n\n".join(b.strip() for b in bodies if b and b.strip())
    return raw_joined, body_joined


def repair_latex_body(body: str, compile_error: str, *, max_tokens: int = 8192):
    prompt = (
        "Sửa phần LaTeX body sau để biên dịch được với XeLaTeX, giữ nguyên nội dung và bố cục form.\n"
        "Yêu cầu:\n"
        "- Chỉ sửa lỗi LaTeX hoặc lỗi định dạng gây compile fail.\n"
        "- Không thêm lời giải thích.\n"
        "- Chỉ trả về body LaTeX đã sửa, không có preamble, không có ```.\n\n"
        "COMPILE ERROR:\n"
        f"{compile_error[-2500:]}\n\n"
        "LATEX BODY:\n"
        f"{body}"
    )
    r = llm_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.0,
        extra={"top_p": 1.0},
        timeout=600,
    )
    if r.status_code != 200:
        raise HTTPException(502, f"LLM repair error {r.status_code}: {r.text[:500]}")
    raw = r.json()["choices"][0]["message"]["content"] or ""
    fixed = strip_wrapping(raw)
    if not fixed.strip():
        raise HTTPException(422, "LLM repair trả về rỗng sau khi strip.")
    return raw, fixed

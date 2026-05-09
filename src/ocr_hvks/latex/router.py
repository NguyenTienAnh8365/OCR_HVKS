"""FastAPI router cho LaTeX/PDF: /latex /pdf /compile /latex/stream /debug/{id}."""

import asyncio
import json
import shutil
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ocr_hvks.config import DEBUG_DIR, LLM_BASE_URL, MODEL_NAME
from ocr_hvks.llm import client as llm_client
from ocr_hvks.latex.compile import compile_pdf, save_debug, save_extra_debug
from ocr_hvks.latex.normalize import strip_wrapping
from ocr_hvks.latex.service import (
    call_llm,
    generate_latex_body,
    repair_latex_body,
)
from ocr_hvks.latex.templates import build_full_tex


router = APIRouter()


class TextIn(BaseModel):
    text: str
    max_tokens: Optional[int] = 16384
    engine: Optional[str] = "xelatex"


class LaTeXIn(BaseModel):
    latex: str
    engine: Optional[str] = "xelatex"
    full_document: Optional[bool] = False


def health() -> dict:
    detail = None
    try:
        models = llm_client.list_models()
        llm_ready = True
    except Exception as e:
        models, llm_ready = [], False
        detail = str(e)
    out = {
        "status": "ok",
        "llm": "ready" if llm_ready else "unreachable",
        "llm_url": LLM_BASE_URL,
        "model_name": MODEL_NAME,
        "models": models,
        "xelatex": shutil.which("xelatex") is not None,
        "lualatex": shutil.which("lualatex") is not None,
    }
    if detail:
        out["detail"] = detail
    return out


@router.post("/latex")
def to_latex(inp: TextIn):
    if not inp.text.strip():
        raise HTTPException(400, "text rỗng")
    t0 = time.time()
    debug_id = uuid.uuid4().hex[:8]
    raw, body = generate_latex_body(inp.text, max_tokens=inp.max_tokens or 16384)
    tex = build_full_tex(body)
    save_debug(debug_id, raw, body, tex)
    return {
        "debug_id": debug_id,
        "raw_len": len(raw),
        "body_len": len(body),
        "raw_head": raw[:400],
        "latex_body": body,
        "full_document": tex,
        "time_s": round(time.time() - t0, 2),
    }


@router.post("/pdf")
def to_pdf(inp: TextIn):
    if not inp.text.strip():
        raise HTTPException(400, "text rỗng")
    debug_id = uuid.uuid4().hex[:8]
    raw, body = generate_latex_body(inp.text, max_tokens=inp.max_tokens or 16384)
    tex_src = build_full_tex(body)
    save_debug(debug_id, raw, body, tex_src)

    try:
        pdf, _ = compile_pdf(tex_src, engine=(inp.engine or "xelatex"), debug_id=debug_id)
    except HTTPException as compile_err:
        compile_detail = str(compile_err.detail)
        save_extra_debug(debug_id, "compile_error.txt", compile_detail)
        repair_raw, repaired_body = repair_latex_body(
            body,
            compile_detail,
            max_tokens=inp.max_tokens or 16384,
        )
        repaired_tex = build_full_tex(repaired_body)
        save_extra_debug(debug_id, "repair.raw.txt", repair_raw)
        save_extra_debug(debug_id, "repaired.body.tex", repaired_body)
        save_extra_debug(debug_id, "repaired.full.tex", repaired_tex)
        pdf, _ = compile_pdf(repaired_tex, engine=(inp.engine or "xelatex"), debug_id=debug_id)

    fname = f"document_{debug_id}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Debug-Id": debug_id},
    )


@router.post("/compile")
def compile_only(inp: LaTeXIn):
    debug_id = uuid.uuid4().hex[:8]
    tex_src = inp.latex if inp.full_document else build_full_tex(strip_wrapping(inp.latex))
    save_debug(debug_id, inp.latex, strip_wrapping(inp.latex), tex_src)
    pdf, _ = compile_pdf(tex_src, engine=(inp.engine or "xelatex"), debug_id=debug_id)
    fname = f"document_{debug_id}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Debug-Id": debug_id},
    )


@router.get("/debug/{debug_id}")
def debug_get(debug_id: str):
    out = {}
    for suffix in (
        "raw.txt",
        "body.tex",
        "full.tex",
        "log",
        "compile_error.txt",
        "repair.raw.txt",
        "repaired.body.tex",
        "repaired.full.tex",
    ):
        p = DEBUG_DIR / f"{debug_id}.{suffix}"
        if p.exists():
            try:
                out[suffix] = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                out[suffix] = f"<read err: {e}>"
        else:
            out[suffix] = None
    if all(v is None for v in out.values()):
        raise HTTPException(404, f"debug_id {debug_id} not found")
    return out


@router.post("/latex/stream")
async def latex_stream(inp: TextIn):
    async def gen():
        if not inp.text.strip():
            yield {"data": json.dumps({"type": "error", "detail": "text rỗng"})}
            return
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None,
            lambda: call_llm(inp.text, stream=True, max_tokens=inp.max_tokens or 16384),
        )
        if r.status_code != 200:
            yield {"data": json.dumps({"type": "error", "detail": f"LLM {r.status_code}"})}
            return
        yield {"data": json.dumps({"type": "start"})}
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
                delta = obj["choices"][0]["delta"].get("content", "")
                if delta:
                    yield {"data": json.dumps({"type": "delta", "text": delta})}
            except Exception:
                continue
        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(gen())

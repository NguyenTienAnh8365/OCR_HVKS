"""FastAPI router cho OCR: /ocr (sync) và /ocr/stream (SSE)."""

import asyncio
import json
import threading
import time
from concurrent.futures import as_completed

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from sse_starlette.sse import EventSourceResponse

from ocr_hvks.config import MODEL_NAME, POPPLER_PATH
from ocr_hvks.llm import client as llm_client
from ocr_hvks.ocr.pdf_loader import (
    count_pdf_pages,
    iter_pdf_pages,
    resolve_pdfinfo,
    resolve_poppler_path,
)
from ocr_hvks.ocr.pipeline import encode_pil, ocr_one_page
from ocr_hvks.ocr.runtime import submit_page


router = APIRouter()

_ALLOWED_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp")


def _validate_file_ext(fname: str) -> None:
    if not any(fname.lower().endswith(ext) for ext in _ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận PDF hoặc ảnh (PNG, JPG, TIFF, BMP, WEBP).")


def health() -> dict:
    pdfinfo_path = resolve_pdfinfo()
    poppler_path = resolve_poppler_path()
    try:
        models = llm_client.list_models()
        return {
            "status": "ok",
            "llm": "ready",
            "models": models,
            "model_name": MODEL_NAME,
            "ocr_output_format": "text",
            "poppler": bool(pdfinfo_path),
            "pdfinfo": pdfinfo_path,
            "poppler_path": poppler_path,
            "poppler_path_raw": POPPLER_PATH,
        }
    except Exception as exc:
        return {
            "status": "ok",
            "llm": "unreachable",
            "detail": str(exc),
            "model_name": MODEL_NAME,
            "ocr_output_format": "text",
            "poppler": bool(pdfinfo_path),
            "pdfinfo": pdfinfo_path,
            "poppler_path": poppler_path,
            "poppler_path_raw": POPPLER_PATH,
        }


@router.post("/ocr")
async def ocr_sync(file: UploadFile = File(...)):
    fname = file.filename or "upload"
    _validate_file_ext(fname)
    data = await file.read()
    try:
        total = count_pdf_pages(data, fname)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not load file: {exc}")

    started_at = time.time()

    def run_pipeline() -> list[dict]:
        # Render chunk → encode → submit vào pool CHUNG (submit_page).
        # submit_page block khi pool đầy → render tự nghẽn theo tốc độ vLLM.
        results_inner: list[dict] = []
        futures = []
        for pnum, img in iter_pdf_pages(data, fname, total=total):
            b64 = encode_pil(img)
            futures.append(submit_page(ocr_one_page, b64, pnum, total, fname))
        for fut in as_completed(futures):
            results_inner.append(fut.result())
        return results_inner

    results = await asyncio.to_thread(run_pipeline)
    results.sort(key=lambda item: item["page"])
    return {
        "filename": fname,
        "total_pages": total,
        "output_format": "text",
        "total_time_s": round(time.time() - started_at, 2),
        "pages": results,
    }


@router.post("/ocr/stream")
async def ocr_stream(request: Request, file: UploadFile = File(...)):
    fname = file.filename or "upload"
    _validate_file_ext(fname)
    data = await file.read()

    async def event_generator():
        try:
            total = count_pdf_pages(data, fname)
        except Exception as exc:
            yield {"data": json.dumps({"type": "error", "detail": str(exc)})}
            return

        yield {
            "data": json.dumps(
                {
                    "type": "start",
                    "total_pages": total,
                    "filename": fname,
                    "output_format": "text",
                }
            )
        }

        started_at = time.time()
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stop_event = threading.Event()

        def run_and_queue(b64: str, pnum: int) -> None:
            if stop_event.is_set():
                return
            result = ocr_one_page(b64, pnum, total, fname)
            asyncio.run_coroutine_threadsafe(queue.put(result), loop)

        cancelled = False

        def render_and_submit() -> None:
            # Chạy trong background thread: render từng chunk → submit ngay vào
            # pool CHUNG. submit_page block khi pool đầy LLM_CONCURRENCY trang
            # → vòng render tự nghẽn theo tốc độ vLLM tiêu thụ (backpressure).
            # stop_event ngắt vòng lặp ngay khi client disconnect, tránh render
            # hết PDF cho 1 SSE đã đóng.
            for pnum, img in iter_pdf_pages(data, fname, total=total):
                if stop_event.is_set():
                    return
                b64 = encode_pil(img)
                if stop_event.is_set():
                    return
                submit_page(run_and_queue, b64, pnum)

        render_task = loop.run_in_executor(None, render_and_submit)

        received = 0
        while received < total:
            try:
                result = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    stop_event.set()
                    cancelled = True
                    break
                continue
            received += 1
            yield {"data": json.dumps({"type": "page", **result})}

        try:
            await render_task
        except Exception:
            pass

        if cancelled:
            return

        yield {
            "data": json.dumps(
                {
                    "type": "done",
                    "output_format": "text",
                    "total_time_s": round(time.time() - started_at, 2),
                }
            )
        }

    return EventSourceResponse(event_generator())

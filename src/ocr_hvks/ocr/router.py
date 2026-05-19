"""FastAPI router cho OCR: /ocr (sync), /ocr/stream (SSE), /ocr/stats."""

import asyncio
import json
import logging
import threading
import time
import uuid
from concurrent.futures import as_completed

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from sse_starlette.sse import EventSourceResponse

from ocr_hvks.config import (
    MAX_PDF_PAGES,
    MAX_UPLOAD_MB,
    MODEL_NAME,
    OCR_REQUEST_TIMEOUT_S,
    POPPLER_PATH,
)
from ocr_hvks.llm import client as llm_client
from ocr_hvks.ocr import metrics
from ocr_hvks.ocr.pdf_loader import (
    count_pdf_pages,
    iter_pdf_pages,
    resolve_pdfinfo,
    resolve_poppler_path,
)
from ocr_hvks.ocr.pipeline import encode_pil, ocr_one_page
from ocr_hvks.ocr.runtime import inflight, submit_page


logger = logging.getLogger("ocr_hvks.ocr")

router = APIRouter()

_ALLOWED_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp")
_MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _validate_file_ext(fname: str) -> None:
    if not any(fname.lower().endswith(ext) for ext in _ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận PDF hoặc ảnh (PNG, JPG, TIFF, BMP, WEBP).")


def _validate_upload_size(data: bytes) -> None:
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File quá lớn ({len(data) // (1024 * 1024)} MB > {MAX_UPLOAD_MB} MB).",
        )


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


@router.get("/ocr/stats")
def ocr_stats() -> dict:
    """Bộ đếm in-memory để quan sát tải OCR trong production."""
    return {**metrics.snapshot(), "inflight_pages": inflight()}


@router.post("/ocr")
async def ocr_sync(file: UploadFile = File(...)):
    rid = uuid.uuid4().hex[:8]
    fname = file.filename or "upload"
    _validate_file_ext(fname)
    data = await file.read()
    _validate_upload_size(data)
    try:
        total = count_pdf_pages(data, fname)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not load file: {exc}")
    if total > MAX_PDF_PAGES:
        raise HTTPException(
            status_code=413,
            detail=f"File quá nhiều trang ({total} > {MAX_PDF_PAGES}).",
        )

    started_at = time.time()
    logger.info("ocr start rid=%s file=%s pages=%d", rid, fname, total)

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

    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(run_pipeline), timeout=OCR_REQUEST_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        metrics.record_request(failed=True)
        logger.warning("ocr timeout rid=%s file=%s pages=%d", rid, fname, total)
        raise HTTPException(status_code=504, detail="OCR quá hạn xử lý.")
    except Exception:
        metrics.record_request(failed=True)
        logger.exception("ocr error rid=%s file=%s", rid, fname)
        raise

    results.sort(key=lambda item: item["page"])
    failed = sum(1 for r in results if not r.get("ok"))
    dur = time.time() - started_at
    metrics.record_request(pages=len(results), pages_failed=failed)
    logger.info(
        "ocr done rid=%s file=%s pages=%d failed=%d dur=%.1fs",
        rid, fname, len(results), failed, dur,
    )
    return {
        "filename": fname,
        "total_pages": total,
        "output_format": "text",
        "total_time_s": round(dur, 2),
        "pages": results,
    }


@router.post("/ocr/stream")
async def ocr_stream(request: Request, file: UploadFile = File(...)):
    rid = uuid.uuid4().hex[:8]
    fname = file.filename or "upload"
    _validate_file_ext(fname)
    data = await file.read()
    _validate_upload_size(data)

    async def event_generator():
        try:
            total = count_pdf_pages(data, fname)
        except Exception as exc:
            yield {"data": json.dumps({"type": "error", "detail": str(exc)})}
            return

        if total > MAX_PDF_PAGES:
            metrics.record_request(failed=True)
            yield {"data": json.dumps({
                "type": "error",
                "detail": f"File quá nhiều trang ({total} > {MAX_PDF_PAGES}).",
            })}
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
        logger.info("ocr/stream start rid=%s file=%s pages=%d", rid, fname, total)
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stop_event = threading.Event()

        def run_and_queue(b64: str, pnum: int) -> None:
            if stop_event.is_set():
                return
            result = ocr_one_page(b64, pnum, total, fname)
            asyncio.run_coroutine_threadsafe(queue.put(result), loop)

        cancelled = False
        timed_out = False

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
        failed = 0
        while received < total:
            try:
                result = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    stop_event.set()
                    cancelled = True
                    break
                if time.time() - started_at > OCR_REQUEST_TIMEOUT_S:
                    stop_event.set()
                    timed_out = True
                    break
                continue
            received += 1
            if not result.get("ok"):
                failed += 1
            yield {"data": json.dumps({"type": "page", **result})}

        try:
            await render_task
        except Exception:
            pass

        dur = time.time() - started_at

        if cancelled:
            metrics.record_request(pages=received, pages_failed=failed)
            logger.info(
                "ocr/stream cancel rid=%s file=%s done=%d/%d dur=%.1fs",
                rid, fname, received, total, dur,
            )
            return

        if timed_out:
            metrics.record_request(pages=received, pages_failed=failed, failed=True)
            logger.warning(
                "ocr/stream timeout rid=%s file=%s done=%d/%d dur=%.1fs",
                rid, fname, received, total, dur,
            )
            yield {"data": json.dumps({"type": "error", "detail": "OCR quá hạn xử lý."})}
            return

        metrics.record_request(pages=received, pages_failed=failed)
        logger.info(
            "ocr/stream done rid=%s file=%s pages=%d failed=%d dur=%.1fs",
            rid, fname, received, failed, dur,
        )
        yield {
            "data": json.dumps(
                {
                    "type": "done",
                    "output_format": "text",
                    "total_time_s": round(dur, 2),
                }
            )
        }

    return EventSourceResponse(event_generator())

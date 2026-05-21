"""FastAPI router cho OCR: /ocr (sync), /ocr/stream (SSE), /ocr/stats."""

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Request
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
    load_all_pages_parallel,
    resolve_pdfinfo,
    resolve_poppler_path,
)
from ocr_hvks.ocr.pipeline import encode_pil, ocr_one_page
from ocr_hvks.ocr.runtime import inflight, submit_page


logger = logging.getLogger("ocr_hvks.ocr")

router = APIRouter()

# Đếm số SSE /ocr/stream connections đang active cùng lúc
_active_streams = 0
_active_streams_lock = threading.Lock()
_active_streams_peak = 0

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
    with _active_streams_lock:
        active = _active_streams
        peak = _active_streams_peak
    return {**metrics.snapshot(), "inflight_pages": inflight(), "active_streams": active, "peak_streams": peak}


@router.post("/ocr")
async def ocr_sync(request: Request):
    form = await request.form(max_part_size=_MAX_UPLOAD_BYTES)
    file = form.get("file")
    if file is None:
        raise HTTPException(status_code=422, detail="Thiếu trường 'file'.")
    rid = uuid.uuid4().hex[:8]
    fname = getattr(file, "filename", None) or "upload"
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
        # Render TẤT CẢ trang song song (tối đa 8 Poppler threads) rồi
        # encode song song (tối đa 8 workers) và flood vLLM trong một đợt.
        _encode_workers = min(os.cpu_count() or 4, 8)
        all_pages = load_all_pages_parallel(data, fname, total=total)
        with ThreadPoolExecutor(max_workers=_encode_workers, thread_name_prefix="enc") as enc_pool:
            b64_list = list(enc_pool.map(encode_pil, [img for _, img in all_pages]))
        futures = [
            submit_page(ocr_one_page, b64, pnum, total, fname)
            for (pnum, _), b64 in zip(all_pages, b64_list)
        ]
        return [fut.result() for fut in as_completed(futures)]

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
async def ocr_stream(request: Request):
    global _active_streams, _active_streams_peak
    form = await request.form(max_part_size=_MAX_UPLOAD_BYTES)
    file = form.get("file")
    if file is None:
        raise HTTPException(status_code=422, detail="Thiếu trường 'file'.")
    rid = uuid.uuid4().hex[:8]
    fname = getattr(file, "filename", None) or "upload"
    _validate_file_ext(fname)
    data = await file.read()
    _validate_upload_size(data)

    with _active_streams_lock:
        _active_streams += 1
        if _active_streams > _active_streams_peak:
            _active_streams_peak = _active_streams
        logger.info("stream open  rid=%s active=%d peak=%d file=%s", rid, _active_streams, _active_streams_peak, fname)

    async def event_generator():
        global _active_streams
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

        timed_out = False

        def render_and_submit() -> None:
            # iter_pdf_pages submit từng chunk ngay khi render xong → vLLM nhận
            # pages liên tục thay vì chờ toàn bộ file render (load_all_pages_parallel
            # delay submission → ít concurrent hơn → KV cache thấp hơn).
            for pnum, img in iter_pdf_pages(data, fname, total=total):
                if stop_event.is_set():
                    return
                b64 = encode_pil(img)
                submit_page(run_and_queue, b64, pnum)

        render_task = loop.run_in_executor(None, render_and_submit)

        received = 0
        failed = 0
        last_ping = time.time()
        try:
            while received < total:
                try:
                    result = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if time.time() - started_at > OCR_REQUEST_TIMEOUT_S:
                        timed_out = True
                        break
                    # Keep-alive: gửi SSE comment mỗi 15s để cloudflare/proxy
                    # không cắt connection khi đang chờ vLLM xử lý trang.
                    if time.time() - last_ping >= 15:
                        yield {"comment": "ping"}
                        last_ping = time.time()
                    continue
                received += 1
                last_ping = time.time()
                if not result.get("ok"):
                    failed += 1
                yield {"data": json.dumps({"type": "page", **result})}

            # render_task có thể đã ném lỗi (poppler hỏng…) → log ra, đừng nuốt.
            try:
                await render_task
            except Exception:
                logger.exception("ocr/stream render lỗi rid=%s file=%s", rid, fname)

            dur = time.time() - started_at
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
        except Exception:
            # Bất kỳ exception nào trong luồng SSE → log full traceback (trước
            # đây bị nuốt nên chỉ thấy "stream đứt" mà không rõ vì sao).
            logger.exception(
                "ocr/stream FAILED rid=%s file=%s done=%d/%d",
                rid, fname, received, total,
            )
            metrics.record_request(pages=received, pages_failed=failed, failed=True)
            yield {"data": json.dumps(
                {"type": "error", "detail": "Lỗi xử lý OCR phía server."}
            )}
        finally:
            # Luôn chạy: client ngắt (GeneratorExit), xong, lỗi, hay quá hạn.
            stop_event.set()
            with _active_streams_lock:
                _active_streams -= 1
                cur = _active_streams
            logger.info(
                "stream close rid=%s active=%d file=%s received=%d/%d timed_out=%s",
                rid, cur, fname, received, total, timed_out,
            )

    return EventSourceResponse(event_generator())

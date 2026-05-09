"""FastAPI router cho OCR: /ocr (sync) và /ocr/stream (SSE)."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, File, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from ocr_hvks.config import MAX_WORKERS, MODEL_NAME, POPPLER_PATH
from ocr_hvks.llm import client as llm_client
from ocr_hvks.ocr.pdf_loader import (
    load_images_from_bytes,
    resolve_pdfinfo,
    resolve_poppler_path,
)
from ocr_hvks.ocr.pipeline import encode_pil, ocr_one_page


router = APIRouter()


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
    data = await file.read()
    fname = file.filename or "upload"
    try:
        pages = load_images_from_bytes(data, fname)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not load file: {exc}")

    total = len(pages)
    work = [(encode_pil(img), pnum, total, fname) for pnum, img in pages]
    started_at = time.time()
    results = []

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total)) as executor:
        futures = [executor.submit(ocr_one_page, *job) for job in work]
        tasks = [loop.run_in_executor(None, lambda future=future: future.result()) for future in futures]
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)

    results.sort(key=lambda item: item["page"])
    return {
        "filename": fname,
        "total_pages": total,
        "output_format": "text",
        "total_time_s": round(time.time() - started_at, 2),
        "pages": results,
    }


@router.post("/ocr/stream")
async def ocr_stream(file: UploadFile = File(...)):
    data = await file.read()
    fname = file.filename or "upload"

    async def event_generator():
        try:
            pages = load_images_from_bytes(data, fname)
        except Exception as exc:
            yield {"data": json.dumps({"type": "error", "detail": str(exc)})}
            return

        total = len(pages)
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
        work = [(encode_pil(img), pnum, total, fname) for pnum, img in pages]
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def run_and_queue(args):
            result = ocr_one_page(*args)
            asyncio.run_coroutine_threadsafe(queue.put(result), loop)

        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total)) as executor:
            for job in work:
                executor.submit(run_and_queue, job)

            received = 0
            while received < total:
                result = await queue.get()
                received += 1
                yield {"data": json.dumps({"type": "page", **result})}

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

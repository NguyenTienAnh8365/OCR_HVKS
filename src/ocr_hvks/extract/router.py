"""FastAPI router cho /extract và /extract/schema."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Body, HTTPException

from ocr_hvks.extract.service import EXTRACT_GROUPS, extract_one_group


router = APIRouter()


@router.get("/extract/schema")
def extract_schema():
    return {
        "groups": [
            {
                "id": g["id"],
                "name": g["name"],
                "file": g["file"],
                "fields": g["fields"],
            }
            for g in EXTRACT_GROUPS
        ]
    }


@router.post("/extract")
def extract(payload: dict = Body(...)):
    text = (payload or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Missing 'text' in request body")
    if not EXTRACT_GROUPS:
        raise HTTPException(status_code=500, detail="No extract schemas loaded")

    started = time.time()
    results: dict = {}
    with ThreadPoolExecutor(max_workers=len(EXTRACT_GROUPS)) as executor:
        futures = {
            executor.submit(extract_one_group, group, text): group["id"]
            for group in EXTRACT_GROUPS
        }
        for future in as_completed(futures):
            gid = futures[future]
            try:
                results[gid] = future.result()
            except Exception as exc:
                results[gid] = {
                    "id": gid,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "fields": [],
                }

    ordered = [results[g["id"]] for g in EXTRACT_GROUPS if g["id"] in results]
    return {
        "total_time_s": round(time.time() - started, 2),
        "groups": ordered,
    }

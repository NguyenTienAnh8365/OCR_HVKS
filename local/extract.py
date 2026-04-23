import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

import vllm_client


EXTRACT_MD_DIR = Path(__file__).parent / "extract_md"
_FIELD_ROW_RE = re.compile(
    r"^\s*\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(Col\s+\d+)\s*\|\s*([^|]*?)\s*\|\s*$"
)
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")
_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def _parse_fields_from_md(md_path: Path):
    fields = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        match = _FIELD_ROW_RE.match(line)
        if not match:
            continue
        ma, ten, col, note = match.groups()
        fields.append({
            "col": col.strip(),
            "ma_truong": ma.strip(),
            "ten_truong": ten.strip(),
            "note": note.strip(),
        })
    return fields


def _load_extract_groups():
    groups = []
    if not EXTRACT_MD_DIR.exists():
        return groups
    for md_path in sorted(EXTRACT_MD_DIR.glob("*.md")):
        fields = _parse_fields_from_md(md_path)
        if not fields:
            continue
        stem = md_path.stem
        display = re.sub(r"^\d+[_\-]+", "", stem).replace("_", " ").strip() or stem
        groups.append({
            "id": stem,
            "name": display,
            "file": md_path.name,
            "md": md_path.read_text(encoding="utf-8"),
            "fields": fields,
        })
    return groups


EXTRACT_GROUPS = _load_extract_groups()


def _build_prompt(group: dict, ocr_text: str) -> str:
    field_list = "\n".join(
        f"- {f['col']} | Mã {f['ma_truong']} | {f['ten_truong']}"
        for f in group["fields"]
    )
    return (
        "Bạn là công cụ trích xuất thông tin từ văn bản tố tụng pháp lý tiếng Việt đã OCR.\n"
        f"Nhóm trường: {group['name']}\n\n"
        "TÀI LIỆU MÔ TẢ TRƯỜNG (Markdown gốc):\n"
        "-----\n"
        f"{group['md']}\n"
        "-----\n\n"
        "DANH SÁCH TRƯỜNG CẦN TRÍCH XUẤT (dùng đúng mã 'Col N' làm khóa JSON):\n"
        f"{field_list}\n\n"
        "VĂN BẢN OCR (nguồn duy nhất để trích xuất):\n"
        "-----\n"
        f"{ocr_text}\n"
        "-----\n\n"
        "YÊU CẦU:\n"
        "- Chỉ được dựa vào VĂN BẢN OCR ở trên; không suy đoán, không bịa.\n"
        "- Nếu trường không có trong văn bản → trả chuỗi rỗng \"\".\n"
        "- Tuân thủ định dạng ghi trong phần 'Quy tắc điền' của tài liệu (ngày dd/mm/yyyy, phân cách `;` cho nhiều tội danh, v.v.).\n"
        "- Giữ nguyên dấu tiếng Việt, không viết hoa toàn bộ.\n\n"
        "ĐẦU RA: chỉ một object JSON hợp lệ, khóa là 'Col N' đúng theo danh sách trên, giá trị là chuỗi.\n"
        "Không thêm lời giải thích, không markdown, không code fence.\n"
    )


def _parse_json_response(text: str) -> dict:
    cleaned = _CODE_FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = _JSON_BLOCK_RE.search(cleaned)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def _extract_one_group(group: dict, ocr_text: str) -> dict:
    started = time.time()
    prompt = _build_prompt(group, ocr_text)
    messages = [{"role": "user", "content": prompt}]

    last_err = "unknown"
    values: dict = {}
    ok = False
    for attempt in range(3):
        try:
            response = vllm_client.chat(
                messages,
                max_tokens=4096,
                temperature=0.0,
                extra={"top_p": 0.8, "repetition_penalty": 1.0},
                timeout=300,
            )
            if response.status_code != 200:
                last_err = f"HTTP {response.status_code}: {response.text[:200]}"
            else:
                payload = response.json()
                if "choices" in payload:
                    raw = payload["choices"][0]["message"]["content"]
                    values = _parse_json_response(raw)
                    ok = True
                    break
                last_err = f"no choices: {str(payload)[:200]}"
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(1.0 * (attempt + 1))

    fields_out = []
    for field in group["fields"]:
        value = values.get(field["col"], "")
        if not isinstance(value, str):
            value = "" if value is None else str(value)
        fields_out.append({
            "col": field["col"],
            "ma_truong": field["ma_truong"],
            "ten_truong": field["ten_truong"],
            "value": value.strip(),
        })

    return {
        "id": group["id"],
        "name": group["name"],
        "file": group["file"],
        "ok": ok,
        "error": None if ok else last_err,
        "time_s": round(time.time() - started, 2),
        "fields": fields_out,
    }


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
        raise HTTPException(status_code=500, detail="No extract_md groups loaded")

    started = time.time()
    results: dict = {}
    with ThreadPoolExecutor(max_workers=len(EXTRACT_GROUPS)) as executor:
        futures = {
            executor.submit(_extract_one_group, group, text): group["id"]
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

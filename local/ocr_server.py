import asyncio
import base64
import json
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
from PIL import Image
from sse_starlette.sse import EventSourceResponse

from config import DPI, MAX_WORKERS, MODEL_NAME, OCR_PORT, POPPLER_PATH
import vllm_client


CODE_FENCE_RE = re.compile(
    r"^\s*```(?:markdown|md|text)?\s*[\r\n]+|[\r\n]+\s*```\s*$",
    re.IGNORECASE,
)


app = FastAPI(title="OCR API (local)", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def encode_pil(img: Image.Image) -> str:
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=95)
    return base64.b64encode(buf.getvalue()).decode()


def clean_output(text: str) -> str:
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?thinking>", "", text, flags=re.IGNORECASE).strip()
    text = CODE_FENCE_RE.sub("", text).strip()
    return text


def resolve_pdfinfo():
    if POPPLER_PATH:
        candidate = shutil.which("pdfinfo", path=POPPLER_PATH)
        if candidate:
            return candidate
    return shutil.which("pdfinfo")


def resolve_poppler_path():
    if not POPPLER_PATH:
        return None
    path = Path(POPPLER_PATH)
    return str(path) if path.exists() else None


def load_images_from_bytes(data: bytes, filename: str):
    if filename.lower().endswith(".pdf"):
        pdfinfo_path = resolve_pdfinfo()
        if not pdfinfo_path:
            raise RuntimeError(
                "Missing Poppler/pdfinfo in PATH. Install Poppler and set POPPLER_PATH if needed."
            )

        kwargs = {"dpi": DPI}
        poppler_path = resolve_poppler_path()
        if poppler_path:
            kwargs["poppler_path"] = poppler_path

        try:
            pages = convert_from_bytes(data, **kwargs)
        except PDFInfoNotInstalledError as exc:
            raise RuntimeError("Poppler/pdfinfo is not available.") from exc
        except PDFPageCountError as exc:
            raise RuntimeError(f"Could not read PDF page count: {exc}") from exc

        return [(index + 1, page.convert("RGB")) for index, page in enumerate(pages)]

    image = Image.open(BytesIO(data)).convert("RGB")
    return [(1, image)]


def build_ocr_prompt(fname: str, page_num: int, total: int) -> str:
    return (

    "Bạn là một công cụ nhận dạng ký tự quang học (OCR) tiếng Việt dành cho các tài liệu pháp lý và tố tụng.\n"

    f"Tệp: {fname} - Trang {page_num}/{total}\n\n"

    "Chỉ trả về kết quả OCR cuối cùng ở định dạng Markdown.\n"

    "Yêu cầu:\n"

    "- Không giải thích. Không chuỗi suy luận. Không sử dụng thẻ XML.\n"
    "- Không bao bọc câu trả lời trong khung mã.\n"
    "- Giữ nguyên cấu trúc gốc càng sát càng tốt.\n"
    "- Chỉ sử dụng tiêu đề, danh sách, bảng và đoạn văn Markdown khi chúng khớp với bản quét.\n"
    "- Giữ các mệnh đề được đánh số, hàng bảng, chữ ký và dấu ngắt dòng rõ ràng trên các dòng riêng biệt.\n"
    "- Không bịa đặt tên, ngày tháng, số tiền hoặc sự kiện pháp lý.\n"
    "- Nếu một số văn bản khó đọc, hãy suy luận một cách thận trọng và giữ cho văn bản không chắc chắn ở mức tối thiểu.\n"
    "- Đầu ra phải chỉ ở định dạng Markdown dễ đọc.\n\n"

    "Quy chuẩn Markdown:\n"
    "- Tiêu đề: dùng #, ##, ### đúng cấp nếu văn bản gốc có tiêu đề rõ ràng.\n"
    "- Đoạn văn: mỗi đoạn cách nhau một dòng trống.\n"
    "- Danh sách:\n"
    "  + Dùng '-' cho danh sách không thứ tự.\n"
    "  + Dùng '1.', '2.', ... cho danh sách có thứ tự, giữ nguyên số gốc nếu có.\n"
    "- Bảng:\n"
    "  + Dùng cú pháp bảng Markdown chuẩn với '|'.\n"
    "  + Giữ nguyên số cột, thứ tự và nội dung.\n"
    "- Xuống dòng:\n"
    "  + Giữ nguyên line break quan trọng (điều khoản, chữ ký, địa điểm, ngày tháng).\n"
    "- Nhấn mạnh:\n"
    "  + Dùng **bold** nếu văn bản gốc in đậm.\n"
    "  + Dùng *italic* nếu văn bản gốc in nghiêng.\n"
    "- Không thêm ký tự trang trí, không tự ý format lại nội dung.\n"
    "- Không gộp dòng hoặc tách dòng nếu không cần thiết.\n"

    )



def build_page_result(page_num: int, value: str, elapsed: float, ok: bool):
    return {
        "page": page_num,
        "text": value,
        "markdown": value,
        "format": "markdown",
        "time_s": round(elapsed, 2),
        "ok": ok,
    }


def ocr_one_page(b64: str, page_num: int, total: int, fname: str):
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
            response = vllm_client.chat(
                messages,
                max_tokens=4096,
                temperature=0.0,
                extra={"repetition_penalty": 1.1, "frequency_penalty": 0.3},
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
                        return build_page_result(page_num, text, time.time() - started_at, True)
                    last_err = f"no choices: {str(payload)[:200]}"
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"

        time.sleep(1.5 * (attempt + 1))

    return build_page_result(page_num, last_err, time.time() - started_at, False)


@app.get("/health")
def health():
    pdfinfo_path = resolve_pdfinfo()
    poppler_path = resolve_poppler_path()
    try:
        models = vllm_client.check_vllm()
        return {
            "status": "ok",
            "vllm": "ready",
            "models": models,
            "model_name": MODEL_NAME,
            "ocr_output_format": "markdown",
            "poppler": bool(pdfinfo_path),
            "pdfinfo": pdfinfo_path,
            "poppler_path": poppler_path,
            "poppler_path_raw": POPPLER_PATH,
        }
    except Exception as exc:
        return {
            "status": "ok",
            "vllm": "unreachable",
            "detail": str(exc),
            "model_name": MODEL_NAME,
            "ocr_output_format": "markdown",
            "poppler": bool(pdfinfo_path),
            "pdfinfo": pdfinfo_path,
            "poppler_path": poppler_path,
            "poppler_path_raw": POPPLER_PATH,
        }


@app.post("/ocr")
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
        "output_format": "markdown",
        "total_time_s": round(time.time() - started_at, 2),
        "pages": results,
    }


@app.post("/ocr/stream")
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
                    "output_format": "markdown",
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
                    "output_format": "markdown",
                    "total_time_s": round(time.time() - started_at, 2),
                }
            )
        }

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=OCR_PORT, log_level="info")

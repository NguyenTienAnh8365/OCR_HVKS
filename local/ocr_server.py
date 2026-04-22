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
        "Bạn là công cụ OCR pháp lý tiếng Việt, tối ưu cho Qwen-VL để đọc văn bản scan "
        "về cáo trạng, quyết định tố tụng, tài liệu điều tra, truy tố và xét xử.\n"
        f"Tệp: {fname} - Trang {page_num}/{total}\n\n"

        "NHIỆM VỤ:\n"
        "- Đọc ảnh và chép lại tối đa trung thành với văn bản gốc.\n"
        "- Ưu tiên tuyệt đối độ đúng của chữ, số, ngày tháng, số hiệu, điều luật, tên cơ quan, họ tên, địa chỉ.\n"
        "- Giữ đúng thứ tự xuất hiện của nội dung trên trang.\n"
        "- Chỉ được phép chép lại những gì nhìn thấy trên ảnh.\n"
        "- Nếu không nhìn thấy hoặc không chắc chắn, KHÔNG được suy đoán.\n"
        "- Không cần sinh Markdown. Trả về văn bản thường, sạch, dễ đọc.\n"
        "- Không giải thích, không bình luận, không mô tả ảnh, không XML, không code fence.\n\n"

        "ƯU TIÊN ĐẶC THÙ VĂN BẢN CÁO TRẠNG, TỐ TỤNG:\n"
        "- Phần mở đầu: quốc hiệu, tiêu ngữ, tên văn bản, cơ quan ban hành.\n"
        "- Căn cứ pháp lý: điều, khoản, điểm, bộ luật, nghị quyết, quyết định.\n"
        "- Số hiệu văn bản, số quyết định, ngày tháng năm, địa danh.\n"
        "- Thông tin bị can, bị cáo, bị hại, người liên quan, nhân chứng.\n"
        "- Hành vi phạm tội: thời gian, địa điểm, diễn biến, phương thức, hậu quả.\n"
        "- Tội danh, điều luật áp dụng, kết luận truy tố, chữ ký, đóng dấu.\n\n"

        "QUY TẮC OCR:\n"
        "- Chép lại nguyên văn tối đa; không tóm tắt, không diễn giải, không viết lại theo ý hiểu.\n"
        "- Không được tự bổ sung nội dung không có trong ảnh, kể cả khi thấy thiếu.\n"
        "- Giữ nguyên dòng, đoạn, danh sách, câu đánh số, tiêu mục nếu nhìn thấy.\n"
        "- Nếu thấy bảng biểu, chép lại theo dạng văn bản giữ đủ dữ liệu; không ép sang Markdown.\n"
        "- Chuẩn hóa nhẹ các lỗi OCR rõ ràng giữa chữ và số nếu chắc chắn từ ngữ cảnh "
        "(ví dụ O/0, I/1, l/1, 2/Z, 5/S); nếu không chắc → giữ nguyên.\n"
        "- Thuật ngữ pháp lý phải đúng chính tả và đúng hoa/thường nếu nhìn thấy rõ.\n"
        "- Nếu một cụm khó đọc hoặc mờ → dùng [không rõ] đúng vị trí.\n"
        "- Nếu mất cả dòng hoặc không thể nhận dạng → dùng [mất dòng].\n"
        "- Không suy diễn nội dung bị thiếu.\n"
        "- Không sinh thêm tiêu đề, không thêm cấu trúc mới nếu không có trên ảnh.\n\n"

        "RÀNG BUỘC CHỐNG HALLUCINATION:\n"
        "- Tuyệt đối không tạo nội dung mới ngoài những gì nhìn thấy.\n"
        "- Không lặp lại chuỗi vô nghĩa, không sinh ký tự bất thường.\n"
        "- Nếu nội dung ngắn hoặc thiếu, vẫn giữ nguyên, không được kéo dài.\n"
        "- Khi không chắc chắn, ưu tiên giữ nguyên hoặc đánh dấu [không rõ], KHÔNG đoán.\n\n"

        "ĐẦU RA MONG MUỐN:\n"
        "- Chỉ trả về nội dung OCR cuối cùng.\n"
        "- Văn bản thường, xuống dòng rõ ràng, giữ bố cục logic của trang.\n"
        "- Không thêm bất kỳ câu dẫn nhập hoặc kết luận nào.\n"
    )


def build_page_result(page_num: int, value: str, elapsed: float, ok: bool):
    return {
        "page": page_num,
        "text": value,
        "format": "text",
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
                temperature=0.05,
                extra={
                    "top_p": 0.8,
                    "repetition_penalty": 1.03,
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
            "ocr_output_format": "text",
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
            "ocr_output_format": "text",
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
        "output_format": "text",
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=OCR_PORT, log_level="info")

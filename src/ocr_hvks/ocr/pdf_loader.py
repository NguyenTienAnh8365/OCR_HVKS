"""Tách PDF/ảnh thành list (page_num, PIL.Image) qua Poppler."""

import os
import shutil
from io import BytesIO
from pathlib import Path
from typing import Iterator

from pdf2image import convert_from_bytes, pdfinfo_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
from PIL import Image

from ocr_hvks.config import DPI, POPPLER_PATH


def resolve_pdfinfo() -> str | None:
    if POPPLER_PATH:
        candidate = shutil.which("pdfinfo", path=POPPLER_PATH)
        if candidate:
            return candidate
    return shutil.which("pdfinfo")


def resolve_poppler_path() -> str | None:
    if not POPPLER_PATH:
        return None
    path = Path(POPPLER_PATH)
    return str(path) if path.exists() else None


def load_images_from_bytes(data: bytes, filename: str) -> list[tuple[int, Image.Image]]:
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


def load_all_pages_parallel(
    data: bytes,
    filename: str,
    total: int | None = None,
) -> list[tuple[int, Image.Image]]:
    """Render toàn bộ PDF song song dùng tối đa CPU cores.

    Khác iter_pdf_pages (chunk_size=8, thread_count=4), hàm này gọi poppler MỘT lần
    với thread_count = số CPU để render tất cả trang đồng thời.
    Với 16 cores: 221 trang render trong ~4-5s thay vì ~41s sequential.
    Đánh đổi: giữ tất cả ảnh trong RAM cùng lúc (~5MB/trang RGB).
    """
    if not filename.lower().endswith(".pdf"):
        return [(1, Image.open(BytesIO(data)).convert("RGB"))]

    if not resolve_pdfinfo():
        raise RuntimeError("Missing Poppler/pdfinfo in PATH.")

    _tc = min(os.cpu_count() or 4, 8)
    kwargs: dict = {"dpi": DPI, "thread_count": _tc}
    poppler_path = resolve_poppler_path()
    if poppler_path:
        kwargs["poppler_path"] = poppler_path

    try:
        pages = convert_from_bytes(data, **kwargs)
    except PDFInfoNotInstalledError as exc:
        raise RuntimeError("Poppler/pdfinfo is not available.") from exc
    except PDFPageCountError as exc:
        raise RuntimeError(f"Could not read PDF page count: {exc}") from exc

    return [(i + 1, img.convert("RGB")) for i, img in enumerate(pages)]


def count_pdf_pages(data: bytes, filename: str) -> int:
    """Trả về số trang PDF (rẻ — chỉ parse header). Ảnh: luôn = 1."""
    if not filename.lower().endswith(".pdf"):
        return 1
    if not resolve_pdfinfo():
        raise RuntimeError("Missing Poppler/pdfinfo in PATH.")
    poppler_path = resolve_poppler_path()
    info = pdfinfo_from_bytes(data, poppler_path=poppler_path) if poppler_path else pdfinfo_from_bytes(data)
    return int(info["Pages"])


def iter_pdf_pages(
    data: bytes,
    filename: str,
    chunk_size: int = 8,
    thread_count: int = 4,
    total: int | None = None,
) -> Iterator[tuple[int, Image.Image]]:
    """Lazy generator yield (page_num, PIL) theo từng chunk.

    Khác load_images_from_bytes: không render cả file 1 lần, mà render chunk_size
    trang một, để caller có thể submit job LLM song song với render chunk tiếp theo.

    `total` có thể được truyền vào nếu caller đã gọi count_pdf_pages trước đó —
    tránh stat poppler lần hai.
    """
    if not filename.lower().endswith(".pdf"):
        yield 1, Image.open(BytesIO(data)).convert("RGB")
        return

    if not resolve_pdfinfo():
        raise RuntimeError("Missing Poppler/pdfinfo in PATH.")

    poppler_path = resolve_poppler_path()
    if total is None:
        total = count_pdf_pages(data, filename)

    render_kwargs = {"dpi": DPI, "thread_count": thread_count}
    if poppler_path:
        render_kwargs["poppler_path"] = poppler_path

    for start in range(1, total + 1, chunk_size):
        end = min(start + chunk_size - 1, total)
        try:
            chunk = convert_from_bytes(
                data, first_page=start, last_page=end, **render_kwargs
            )
        except PDFInfoNotInstalledError as exc:
            raise RuntimeError("Poppler/pdfinfo is not available.") from exc
        except PDFPageCountError as exc:
            raise RuntimeError(f"Could not read PDF page count: {exc}") from exc
        for i, img in enumerate(chunk):
            yield start + i, img.convert("RGB")

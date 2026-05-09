"""Tách PDF/ảnh thành list (page_num, PIL.Image) qua Poppler."""

import shutil
from io import BytesIO
from pathlib import Path

from pdf2image import convert_from_bytes
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

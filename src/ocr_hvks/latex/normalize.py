"""Tiền xử lý OCR text trước khi build LaTeX prompt."""

import re


PAGE_MARKER_RE = re.compile(r"(?m)^\s*---\s*Trang\s+(\d+)\s*---\s*$")

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_OPEN_RE = re.compile(r"^\s*```(?:latex|tex)?\s*\n", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"\n?\s*```\s*$")
_DOC_RE = re.compile(r"\\begin\{document\}(.*?)\\end\{document\}", re.DOTALL)
_STANDALONE_PAGE_RE = re.compile(r"^\s*(\d{1,3})\s*$")
_ROMAN_SECTION_RE = re.compile(r"^(?:[IVXLC]+)\.\s+")
_NUMBERED_ITEM_RE = re.compile(r"^\d+\)\s+")
_PLUS_ITEM_RE = re.compile(r"^[+•-]\s+")


def strip_wrapping(latex: str) -> str:
    if not latex:
        return ""
    latex = _THINK_RE.sub("", latex).strip()
    latex = _FENCE_OPEN_RE.sub("", latex)
    latex = _FENCE_CLOSE_RE.sub("", latex).strip()
    m = _DOC_RE.search(latex)
    if m:
        latex = m.group(1).strip()
    return latex


def split_legal_markers(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n")
    text = re.sub(
        r"(C[ỘO]NG\s+HO[ÀA]\s+X[ÃA]\s+H[ỘO]I\s+CH[ỦU]\s+NGH[ĨI]A\s+VI[ỆE]T\s+NAM)\s+(Đ[ỘO]c\s+l[ậa]p\s*-\s*T[ựu]\s+do\s*-\s*H[ạa]nh\s+ph[úu]c)",
        r"\1\n\2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s+(?=(Bản án số\s*:|Thụ lý số\s*:|Vụ\s*:|can tội\s*:|Lưu HS\b))",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+(?=(Ngày\s+\d))", "\n", text, flags=re.IGNORECASE)
    return text


def cleanup_ocr_punctuation(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+([,.;:?!])", r"\1", text)
    text = re.sub(r"([,.;:?!])\s+([,.;:?!])", r"\2", text)
    text = text.replace("./.", ".")
    text = text.replace(". /.", ".")
    text = text.replace(",.", ",")
    text = text.replace(":.", ":")
    text = text.replace(";.", ";")
    text = re.sub(r"\.{2,}", ".", text)
    return text


def normalize_ocr_input(text: str) -> str:
    if not text:
        return ""
    cleaned = cleanup_ocr_punctuation(text)
    src_lines = [ln.strip() for ln in split_legal_markers(cleaned).split("\n")]
    out: list[str] = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            out.append(current.strip())
        current = ""

    for line in src_lines:
        if not line:
            flush()
            continue

        if _STANDALONE_PAGE_RE.match(line):
            flush()
            continue

        starts_block = (
            _ROMAN_SECTION_RE.match(line)
            or _NUMBERED_ITEM_RE.match(line)
            or _PLUS_ITEM_RE.match(line)
        )
        if starts_block:
            flush()
            current = line
            flush()
            continue

        if not current:
            current = line
            continue

        current = f"{current} {line}"

    flush()
    return "\n\n".join(out).strip()


def split_ocr_by_page(text: str, pages_per_chunk: int):
    """Split OCR text by '--- Trang N ---' markers, then pack `pages_per_chunk`
    pages into one chunk. Returns list of (chunk_text, [page_nums])."""
    if not text or not text.strip():
        return []

    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        return [(text.strip(), [1])]

    pages = []
    if matches[0].start() > 0:
        prefix = text[: matches[0].start()].strip()
        if prefix:
            pages.append((0, prefix))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            pages.append((int(m.group(1)), body))

    if not pages:
        return []

    n = max(1, pages_per_chunk)
    chunks = []
    for i in range(0, len(pages), n):
        group = pages[i:i + n]
        chunk_text = "\n\n".join(body for _, body in group)
        chunks.append((chunk_text, [pnum for pnum, _ in group]))
    return chunks

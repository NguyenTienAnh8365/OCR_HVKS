import re
import time
import json
import uuid
import shutil
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from config import LATEX_PORT, DEBUG_DIR, MODEL_NAME, VLLM_BASE_URL
import vllm_client


SYSTEM_PROMPT = (
    "Bạn là biên tập viên tiếng Việt kiêm chuyên gia LaTeX cho văn bản tố tụng, hành chính và biểu mẫu pháp lý.\n"
    "Nhiệm vụ:\n"
    "1. Nhận văn bản đã OCR (markdown hoặc plain text) — có thể sai chính tả, thiếu dấu, lộn dòng, ký tự nhiễu.\n"
    "2. Sửa chính tả, dấu câu, lỗi OCR rõ ràng. TUYỆT ĐỐI KHÔNG thêm nội dung không có trong bản gốc, không tóm tắt, không dịch, không bịa số liệu.\n"
    "3. Ưu tiên GIỮ ĐÚNG BỐ CỤC FORM của bản gốc. Với biên bản, bản án, quyết định, phần ký tên, sao y, tiêu đề giữa trang: không tự ý biến mọi thứ thành \\section/\\subsection.\n"
    "4. Chỉ dùng \\section/\\subsection khi bản gốc thực sự là tài liệu có mục rõ ràng. Nếu là form chuẩn thì giữ bố cục dòng, khối, căn trái/phải, tiêu đề giữa trang.\n"
    "5. Dòng điền chỗ trống dùng \\dotfill, \\underline{\\hspace{...}} hoặc \\rule{...}{0.4pt}; KHÔNG dùng nhiều dấu chấm liên tiếp như .... thay cho \\dotfill.\n"
    "6. Nếu có tiêu đề form độc lập như 'SAO Y BẢN CHÍNH', 'BIÊN BẢN', 'QUYẾT ĐỊNH', 'BẢN ÁN', ưu tiên dùng \\formtitle{...}.\n"
    "7. Nếu ở đầu trang có tiêu ngữ hai khối song song: bên trái là cơ quan như 'TOÀ ÁN NHÂN DÂN TỈNH GIA LAI', bên phải là quốc hiệu/tiêu ngữ như 'CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM' và 'Độc lập - Tự do - Hạnh phúc', hãy tách thành hai khối trái/phải bằng \\headerpair{left}{right}. Dòng 'Độc lập - Tự do - Hạnh phúc' LUÔN đi cùng khối quốc hiệu bên phải, xuống dòng bằng \\\\ và căn giữa trong khối phải bằng \\centering.\n"
    "8. Nếu có hai khối ký tên song song trái/phải như 'HỘI THẨM NHÂN DÂN' và 'CHỦ TỌA PHIÊN TÒA', dùng \\signaturepair{title trái}{subtitle trái}{tên trái}{title phải}{subtitle phải}{tên phải}.\n"
    "9. Các cặp metadata song song như 'Bản án số: ...' và 'Ngày ...' phải dùng tabular không border, không dùng \\hfill trong văn bản thuần.\n"
    "10. Các dòng metadata như 'Bản án số:', 'Ngày ...', 'Thụ lý số:', 'Vụ:', 'can tội:', 'Lưu HS' phải tách thành các dòng riêng; không dồn nhiều nhãn vào một dòng nếu bản gốc là form.\n"
    "11. Dòng số trang đứng riêng phải giữ thành một dòng riêng, ưu tiên dùng \\pagenote{...}. Dòng ký tên '(Đã ký)' phải đi cùng đúng khối ký tương ứng.\n"
    "12. Nếu một khối ký có nhiều người ký, trong đối số tên của \\signaturepair phải ngắt bằng \\\\ giữa các tên; KHÔNG nối nhiều tên bằng dấu phẩy.\n"
    "13. Phải sửa các lỗi dấu câu OCR rõ ràng như './.', '..', ',.', '. ,' thành dấu câu chuẩn; không để thừa dấu ở cuối câu.\n"
    "14. Danh sách dùng itemize/enumerate; bảng dùng tabular; in đậm dùng \\textbf; in nghiêng dùng \\textit; công thức toán dùng \\(...\\) hoặc \\[...\\].\n"
    "15. Escape đúng các ký tự đặc biệt LaTeX: % $ & # _ { } ~ ^ \\ .\n"
    "16. CHỈ trả về phần NỘI DUNG LaTeX (những gì nằm giữa \\begin{document} và \\end{document}), KHÔNG kèm \\documentclass, KHÔNG kèm preamble, KHÔNG kèm ``` hoặc giải thích.\n"
    "17. KHÔNG viết <think>, không viết suy nghĩ. Trả lời trực tiếp bằng LaTeX hợp lệ, ưu tiên đầu ra ổn định, ít sáng tác."
)

LATEX_PREAMBLE = r"""\documentclass[12pt,a4paper]{article}
\usepackage{fontspec}
\defaultfontfeatures{Ligatures=TeX}
\setmainfont{DejaVu Serif}
\setsansfont{DejaVu Sans}
\setmonofont{DejaVu Sans Mono}
\usepackage[margin=2.2cm]{geometry}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{array,booktabs,longtable}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{soul}
\setlength{\parindent}{0pt}
\setuldepth{strut}
\newcommand{\headerpair}[2]{%
\noindent
\begin{minipage}[t]{0.48\textwidth}
\centering\small
#1\par
\end{minipage}\hfill
\begin{minipage}[t]{0.48\textwidth}
\centering\small
#2\par
\end{minipage}
\vspace{0.35cm}}
\newcommand{\formtitle}[1]{%
\vspace{0.3cm}
\begin{center}
\textbf{\large\MakeUppercase{#1}}
\end{center}
\vspace{0.2cm}}
\newcommand{\signaturepair}[6]{%
\vspace{0.8cm}
\noindent
\begin{minipage}[t]{0.46\textwidth}
\centering
\textbf{#1}\par
\vspace{0.1cm}
#2\par
\vspace{1.8cm}
{\textit{#3}\par}
\end{minipage}\hfill
\begin{minipage}[t]{0.46\textwidth}
\centering
\textbf{#4}\par
\vspace{0.1cm}
#5\par
\vspace{1.8cm}
{\textit{#6}\par}
\end{minipage}}
\newcommand{\pagenote}[1]{\begin{center}#1\end{center}}
\begin{document}
"""
LATEX_POSTAMBLE = "\n\\end{document}\n"


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_OPEN_RE = re.compile(r"^\s*```(?:latex|tex)?\s*\n", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"\n?\s*```\s*$")
_DOC_RE = re.compile(r"\\begin\{document\}(.*?)\\end\{document\}", re.DOTALL)
_STANDALONE_PAGE_RE = re.compile(r"^\s*(\d{1,3})\s*$")
_ROMAN_SECTION_RE = re.compile(r"^(?:[IVXLC]+)\.\s+")
_NUMBERED_ITEM_RE = re.compile(r"^\d+\)\s+")
_PLUS_ITEM_RE = re.compile(r"^[+•-]\s+")
_FORM_TITLES = {
    "SAO Y BẢN CHÍNH",
    "BIÊN BẢN",
    "QUYẾT ĐỊNH",
    "BẢN ÁN",
    "CÁO TRẠNG",
    "THÔNG BÁO",
}

LATEX_EXAMPLE = r"""
VÍ DỤ ĐẦU RA CHUẨN:

\headerpair{
  \textbf{CÔNG AN TỈNH GIA LAI}\\
  Cơ quan CSĐT\\
  Số: 112/KLĐT
}{
  \centering
  \textbf{CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM}\\
  \textit{Độc lập -- Tự do -- Hạnh phúc}\\
  Pleiku, ngày 20 tháng 10 năm 2003
}

\formtitle{Bản Kết Luận Điều Tra}

\noindent Họ và tên: Nguyễn Văn Trọng \dotfill\\
\begin{tabular}{@{}p{0.48\textwidth}p{0.48\textwidth}@{}}
Sinh ngày: 15/05/1984 & Nơi sinh: Thị trấn Chư Prông \\
\end{tabular}

\begin{tabular}{@{}p{0.48\textwidth}p{0.48\textwidth}@{}}
Bản án số: 12/HS-ST & Ngày 25-02-2004 \\
\end{tabular}

\signaturepair{HỘI THẨM NHÂN DÂN}{(Đã ký)}{Nguyễn Thành Long \\ Dương Chí Trực}
              {CHỦ TOẠ PHIÊN TOÀ}{(Đã ký)}{Nguyễn Thị Xuân Hương}

\vspace{1cm}
\noindent\rule{\textwidth}{0.4pt}

\formtitle{Sao Y Bản Chính}

VÍ DỤ ĐẦU TRANG BẢN ÁN:

\headerpair{
  \textbf{TOÀ ÁN NHÂN DÂN TỈNH GIA LAI}
}{
  \centering
  \textbf{CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM}\\
  \textit{Độc lập -- Tự do -- Hạnh phúc}
}

\begin{tabular}{@{}p{0.48\textwidth}p{0.48\textwidth}@{}}
Bản án số: 12/HS-ST & Ngày 25-02-2004 \\
Thụ lý số: 181/HS-ST & Ngày 13-11-2003 \\
\end{tabular}

\noindent Vụ: Nguyễn Văn Trọng và đồng bọn\\
\noindent Can tội: ``Cố ý gây thương tích''\\
\noindent Lưu HS
"""


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
    out = []
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


def build_full_tex(body: str) -> str:
    return LATEX_PREAMBLE + body.strip() + LATEX_POSTAMBLE


def build_latex_request(user_text: str) -> str:
    return (
        "Chuyển đoạn OCR sau thành LaTeX hợp lệ, biên dịch được và giữ bố cục form pháp lý.\n"
        "Lưu ý:\n"
        "- Ưu tiên form gốc hơn là chia section.\n"
        "- Dòng điền chỗ trống phải dùng \\dotfill, \\underline{\\hspace{...}} hoặc \\rule, không dùng '....'.\n"
        "- Nếu phần đầu trang có cơ quan bên trái và quốc hiệu/tiêu ngữ Việt Nam bên phải, dùng \\headerpair{left}{right}. Cả hai khối phải được căn giữa trong nửa trang của mình; khối bên phải cần để 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM' và 'Độc lập -- Tự do -- Hạnh phúc' đi cùng nhau, xuống dòng bằng \\\\.\n"
        "- Nếu có khối ký trái/phải song song thì dùng \\signaturepair{title trái}{subtitle trái}{tên trái}{title phải}{subtitle phải}{tên phải}. Mỗi khối phải căn giữa ổn định theo cột.\n"
        "- Nếu một khối ký có nhiều người ký, tên trong đối số thứ 3 hoặc thứ 6 phải ngắt bằng \\\\, không nối bằng dấu phẩy.\n"
        "- Metadata song song như 'Bản án số ...' và 'Ngày ...' phải dùng tabular không border: \\begin{tabular}{@{}p{0.48\\textwidth}p{0.48\\textwidth}@{}} ... & ... \\\\ \\end{tabular}.\n"
        "- KHÔNG dùng \\hfill trong dòng văn bản thuần để ép metadata hai đầu.\n"
        "- Metadata đầu văn bản như 'Bản án số', 'Ngày', 'Thụ lý số', 'Vụ', 'can tội', 'Lưu HS' phải thành các dòng riêng của form, không dồn thành một câu dài.\n"
        "- Khi OCR cho ra một dòng dính như 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM Độc lập - Tự do - Hạnh phúc', phải tách thành 2 dòng trong cùng khối phải.\n"
        "- Khi OCR cho ra một dòng dính như 'Thụ lý số ... Ngày ... Vụ ... can tội ...', phải tách lại thành nhiều dòng hoặc tabular đúng form.\n"
        "- Phải sửa lỗi dấu câu OCR rõ ràng như './.', '..', ',.' trước khi dựng LaTeX.\n"
        "- Tiêu đề độc lập ở giữa trang như 'SAO Y BẢN CHÍNH' dùng \\formtitle{...}.\n"
        "- Dòng số trang đứng riêng dùng \\pagenote{...} hoặc một block center riêng.\n"
        "- Mỗi mục lớn như 'I.', 'II.' phải thành một đoạn riêng.\n"
        "- Mỗi mục đánh số như '1)', '2)' phải xuống dòng riêng.\n"
        "- Mỗi dòng nhân sự bắt đầu bằng '+' phải là một dòng hoặc một đoạn riêng, không dồn chung.\n"
        "- Không thêm giải thích.\n\n"
        + LATEX_EXAMPLE
        + "\n\nOCR INPUT:\n"
        + user_text
    )


def compile_pdf(tex_source: str, engine: str = "xelatex", debug_id: Optional[str] = None):
    if shutil.which(engine) is None:
        raise HTTPException(500, f"{engine} không có trong PATH. Cài MiKTeX/TeX Live trên Windows.")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        tex_file = td_path / "doc.tex"
        tex_file.write_text(tex_source, encoding="utf-8")
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error",
               "-output-directory", str(td_path), str(tex_file)]
        last = None
        for _ in range(2):
            try:
                last = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            except subprocess.TimeoutExpired as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"{engine} timeout sau 180s. stdout_tail={str(getattr(e, 'stdout', '') or '')[-1000:]}",
                ) from e
            if last.returncode != 0:
                break
        pdf_file = td_path / "doc.pdf"
        log_file = td_path / "doc.log"
        log_txt = ""
        if log_file.exists():
            try:
                log_txt = log_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        if debug_id:
            try:
                (DEBUG_DIR / f"{debug_id}.log").write_text(log_txt, encoding="utf-8")
            except Exception:
                pass
        if not pdf_file.exists():
            raise HTTPException(
                status_code=500,
                detail=f"{engine} failed.\nSTDOUT:\n{(last.stdout if last else '')[-2000:]}\n\nLOG:\n{log_txt[-4000:]}",
            )
        return pdf_file.read_bytes(), log_txt[-2000:]


def save_debug(debug_id: str, raw: str, body: str, tex: str):
    try:
        (DEBUG_DIR / f"{debug_id}.raw.txt").write_text(raw or "", encoding="utf-8")
        (DEBUG_DIR / f"{debug_id}.body.tex").write_text(body or "", encoding="utf-8")
        (DEBUG_DIR / f"{debug_id}.full.tex").write_text(tex or "", encoding="utf-8")
    except Exception as e:
        print("save_debug err:", e)


def save_extra_debug(debug_id: str, suffix: str, content: str):
    try:
        (DEBUG_DIR / f"{debug_id}.{suffix}").write_text(content or "", encoding="utf-8")
    except Exception as e:
        print("save_extra_debug err:", e)


def call_llm(user_text: str, *, stream: bool = False, max_tokens: int = 16384):
    normalized_input = normalize_ocr_input(user_text)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_latex_request(normalized_input)},
    ]
    return vllm_client.chat(
        messages,
        max_tokens=max_tokens,
        temperature=0.0,
        stream=stream,
        extra={"top_p": 1.0},
        timeout=600,
    )


def generate_latex_body(user_text: str, *, max_tokens: int = 16384, retries: int = 2):
    last_status = None
    last_detail = "unknown"
    last_raw = ""
    last_body = ""

    for attempt in range(retries + 1):
        try:
            r = call_llm(user_text, stream=False, max_tokens=max_tokens)
            last_status = r.status_code
            if r.status_code != 200:
                last_detail = f"vLLM error {r.status_code}: {r.text[:500]}"
            else:
                data = r.json()
                choice = data["choices"][0]
                last_raw = choice["message"]["content"] or ""
                finish_reason = choice.get("finish_reason", "")
                last_body = strip_wrapping(last_raw)
                if finish_reason == "length":
                    print(f"[WARN] attempt={attempt} finish_reason=length — output bị cắt do max_tokens={max_tokens}. raw_len={len(last_raw)}")
                if last_body.strip() and finish_reason != "length":
                    return last_raw, last_body
                if finish_reason == "length" and attempt == retries:
                    last_detail = f"Output bị cắt (finish_reason=length, max_tokens={max_tokens}). Tăng max_tokens hoặc chia nhỏ input. raw_len={len(last_raw)}"
                elif not last_body.strip():
                    last_detail = f"LLM trả về rỗng sau khi strip. raw_head={last_raw[:400]!r}"
        except Exception as e:
            last_detail = f"{type(e).__name__}: {e}"

        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    status_code = 422 if last_status == 200 else 502
    raise HTTPException(status_code=status_code, detail=last_detail)


def repair_latex_body(body: str, compile_error: str, *, max_tokens: int = 8192):
    prompt = (
        "Sửa phần LaTeX body sau để biên dịch được với XeLaTeX, giữ nguyên nội dung và bố cục form.\n"
        "Yêu cầu:\n"
        "- Chỉ sửa lỗi LaTeX hoặc lỗi định dạng gây compile fail.\n"
        "- Không thêm lời giải thích.\n"
        "- Chỉ trả về body LaTeX đã sửa, không có preamble, không có ```.\n\n"
        "COMPILE ERROR:\n"
        f"{compile_error[-2500:]}\n\n"
        "LATEX BODY:\n"
        f"{body}"
    )
    r = vllm_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.0,
        extra={"top_p": 1.0},
        timeout=600,
    )
    if r.status_code != 200:
        raise HTTPException(502, f"vLLM repair error {r.status_code}: {r.text[:500]}")
    raw = r.json()["choices"][0]["message"]["content"] or ""
    fixed = strip_wrapping(raw)
    if not fixed.strip():
        raise HTTPException(422, "LLM repair trả về rỗng sau khi strip.")
    return raw, fixed


app = FastAPI(title="LaTeX & PDF Server (local)", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


class TextIn(BaseModel):
    text: str
    max_tokens: Optional[int] = 16384
    engine: Optional[str] = "xelatex"


class LaTeXIn(BaseModel):
    latex: str
    engine: Optional[str] = "xelatex"
    full_document: Optional[bool] = False


@app.get("/health")
def health():
    detail = None
    try:
        models = vllm_client.check_vllm()
        vllm_ready = True
    except Exception as e:
        models, vllm_ready = [], False
        detail = str(e)
    out = {
        "status": "ok",
        "vllm": "ready" if vllm_ready else "unreachable",
        "vllm_url": VLLM_BASE_URL,
        "model_name": MODEL_NAME,
        "models": models,
        "xelatex": shutil.which("xelatex") is not None,
        "lualatex": shutil.which("lualatex") is not None,
    }
    if detail:
        out["detail"] = detail
    return out


@app.post("/latex")
def to_latex(inp: TextIn):
    if not inp.text.strip():
        raise HTTPException(400, "text rỗng")
    t0 = time.time()
    debug_id = uuid.uuid4().hex[:8]
    raw, body = generate_latex_body(inp.text, max_tokens=inp.max_tokens or 16384)
    tex = build_full_tex(body)
    save_debug(debug_id, raw, body, tex)
    return {
        "debug_id": debug_id,
        "raw_len": len(raw),
        "body_len": len(body),
        "raw_head": raw[:400],
        "latex_body": body,
        "full_document": tex,
        "time_s": round(time.time() - t0, 2),
    }


@app.post("/pdf")
def to_pdf(inp: TextIn):
    if not inp.text.strip():
        raise HTTPException(400, "text rỗng")
    debug_id = uuid.uuid4().hex[:8]
    raw, body = generate_latex_body(inp.text, max_tokens=inp.max_tokens or 16384)
    tex_src = build_full_tex(body)
    save_debug(debug_id, raw, body, tex_src)

    try:
        pdf, _ = compile_pdf(tex_src, engine=(inp.engine or "xelatex"), debug_id=debug_id)
    except HTTPException as compile_err:
        compile_detail = str(compile_err.detail)
        save_extra_debug(debug_id, "compile_error.txt", compile_detail)
        repair_raw, repaired_body = repair_latex_body(
            body,
            compile_detail,
            max_tokens=inp.max_tokens or 16384,
        )
        repaired_tex = build_full_tex(repaired_body)
        save_extra_debug(debug_id, "repair.raw.txt", repair_raw)
        save_extra_debug(debug_id, "repaired.body.tex", repaired_body)
        save_extra_debug(debug_id, "repaired.full.tex", repaired_tex)
        pdf, _ = compile_pdf(repaired_tex, engine=(inp.engine or "xelatex"), debug_id=debug_id)

    fname = f"document_{debug_id}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Debug-Id": debug_id},
    )


@app.post("/compile")
def compile_only(inp: LaTeXIn):
    debug_id = uuid.uuid4().hex[:8]
    tex_src = inp.latex if inp.full_document else build_full_tex(strip_wrapping(inp.latex))
    save_debug(debug_id, inp.latex, strip_wrapping(inp.latex), tex_src)
    pdf, _ = compile_pdf(tex_src, engine=(inp.engine or "xelatex"), debug_id=debug_id)
    fname = f"document_{debug_id}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"',
                 "X-Debug-Id": debug_id},
    )


@app.get("/debug/{debug_id}")
def debug_get(debug_id: str):
    out = {}
    for suffix in (
        "raw.txt",
        "body.tex",
        "full.tex",
        "log",
        "compile_error.txt",
        "repair.raw.txt",
        "repaired.body.tex",
        "repaired.full.tex",
    ):
        p = DEBUG_DIR / f"{debug_id}.{suffix}"
        if p.exists():
            try:
                out[suffix] = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                out[suffix] = f"<read err: {e}>"
        else:
            out[suffix] = None
    if all(v is None for v in out.values()):
        raise HTTPException(404, f"debug_id {debug_id} not found")
    return out


@app.post("/latex/stream")
async def latex_stream(inp: TextIn):
    async def gen():
        if not inp.text.strip():
            yield {"data": json.dumps({"type": "error", "detail": "text rỗng"})}
            return
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None,
            lambda: call_llm(inp.text, stream=True, max_tokens=inp.max_tokens or 16384),
        )
        if r.status_code != 200:
            yield {"data": json.dumps({"type": "error", "detail": f"vLLM {r.status_code}"})}
            return
        yield {"data": json.dumps({"type": "start"})}
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
                delta = obj["choices"][0]["delta"].get("content", "")
                if delta:
                    yield {"data": json.dumps({"type": "delta", "text": delta})}
            except Exception:
                continue
        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(gen())


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=LATEX_PORT, log_level="info")

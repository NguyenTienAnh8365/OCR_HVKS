"""Compile LaTeX → PDF qua xelatex (subprocess) + lưu debug."""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from ocr_hvks.config import DEBUG_DIR


def compile_pdf(tex_source: str, engine: str = "xelatex",
                debug_id: Optional[str] = None) -> tuple[bytes, str]:
    if shutil.which(engine) is None:
        raise HTTPException(500, f"{engine} không có trong PATH. Cài MiKTeX/TeX Live.")

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


def save_debug(debug_id: str, raw: str, body: str, tex: str) -> None:
    try:
        (DEBUG_DIR / f"{debug_id}.raw.txt").write_text(raw or "", encoding="utf-8")
        (DEBUG_DIR / f"{debug_id}.body.tex").write_text(body or "", encoding="utf-8")
        (DEBUG_DIR / f"{debug_id}.full.tex").write_text(tex or "", encoding="utf-8")
    except Exception as e:
        print("save_debug err:", e)


def save_extra_debug(debug_id: str, suffix: str, content: str) -> None:
    try:
        (DEBUG_DIR / f"{debug_id}.{suffix}").write_text(content or "", encoding="utf-8")
    except Exception as e:
        print("save_extra_debug err:", e)

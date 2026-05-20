"""Combined FastAPI app — gắn 3 router OCR/Extract/LaTeX và /health tổng."""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ocr_hvks import __version__
from ocr_hvks.extract.router import router as extract_router
from ocr_hvks.latex.router import health as latex_health
from ocr_hvks.latex.router import router as latex_router
from ocr_hvks.ocr.router import health as ocr_health
from ocr_hvks.ocr.router import router as ocr_router


# uvicorn KHÔNG cấu hình root logger → logger.info() của app (vd "ocr/stream
# start/done") bị nuốt, journald không thấy gì. Gắn handler riêng cho cây
# logger "ocr_hvks" để log app thật sự hiện ra (journald đọc stdout).
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s", "%H:%M:%S")
)
_app_logger = logging.getLogger("ocr_hvks")
if not _app_logger.handlers:
    _app_logger.addHandler(_log_handler)
_app_logger.setLevel(logging.INFO)
_app_logger.propagate = False


def create_app() -> FastAPI:
    app = FastAPI(title="OCR_HVKS API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ocr_router)
    app.include_router(extract_router)
    app.include_router(latex_router)

    @app.get("/health")
    def combined_health():
        ocr = ocr_health()
        latex = latex_health()
        llm_ready = ocr.get("llm") == "ready" and latex.get("llm") == "ready"
        return {
            "status": "ok",
            "ocr": ocr,
            "latex": latex,
            "llm": "ready" if llm_ready else "unreachable",
            "xelatex": bool(latex.get("xelatex")),
            "model_name": latex.get("model_name") or ocr.get("model_name"),
        }

    return app


app = create_app()

# run
# chmod +x deploy/*.sh && ./deploy/start_vllm.sh
# chmod +x deploy/*.sh && ./deploy/start_api.sh


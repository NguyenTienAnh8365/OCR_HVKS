"""Entrypoint chạy uvicorn — `python -m ocr_hvks.server` hoặc `ocr-hvks-server`."""

import uvicorn

from ocr_hvks.config import API_HOST, API_PORT


def main() -> None:
    uvicorn.run(
        "ocr_hvks.api.app:app",
        host=API_HOST,
        port=API_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()

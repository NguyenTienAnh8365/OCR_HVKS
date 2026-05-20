"""Bộ đếm in-memory cho OCR — phục vụ endpoint /ocr/stats để quan sát tải.

Cố ý giữ tối giản (không kéo Prometheus): vài counter + lock, đủ để thấy
production nội bộ đang chạy ra sao (đã xử lý bao nhiêu, lỗi bao nhiêu).
Counter reset khi restart process — không bền, không phải mục tiêu.
"""

import threading
import time

_lock = threading.Lock()
_started_at = time.time()
_c = {
    "requests_total": 0,    # số job OCR đã nhận
    "requests_failed": 0,   # job lỗi hẳn (exception / quá hạn)
    "pages_total": 0,       # tổng trang đã OCR xong
    "pages_failed": 0,      # trang trả về ok=False
}


def record_request(*, pages: int = 0, pages_failed: int = 0,
                    failed: bool = False) -> None:
    """Ghi nhận một job OCR vừa kết thúc."""
    with _lock:
        _c["requests_total"] += 1
        if failed:
            _c["requests_failed"] += 1
        _c["pages_total"] += pages
        _c["pages_failed"] += pages_failed


def snapshot() -> dict:
    """Bản chụp counter hiện tại (kèm uptime)."""
    with _lock:
        snap = dict(_c)
    snap["uptime_s"] = round(time.time() - _started_at, 1)
    return snap

"""Tài nguyên OCR dùng chung toàn app: một ThreadPoolExecutor + semaphore
giới hạn tổng tải gửi lên vLLM.

Trước đây mỗi request /ocr tự tạo một ThreadPoolExecutor riêng → nhiều user
gửi cùng lúc thì hàng nghìn lời gọi dồn vào vLLM, vượt xa khả năng phục vụ,
chỉ làm phình hàng đợi và kéo tail latency.

Giờ mọi request submit job OCR-trang qua submit_page() vào MỘT pool chung.
Tổng số trang đang gọi vLLM đồng thời bị chặn cứng ở LLM_CONCURRENCY, bất kể
bao nhiêu request đến — đây là backpressure cho cả hệ thống.
"""

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from ocr_hvks.config import LLM_CONCURRENCY

# Pool dùng chung. max_workers = trần số trang chạy LLM đồng thời.
_executor = ThreadPoolExecutor(
    max_workers=LLM_CONCURRENCY,
    thread_name_prefix="ocr-llm",
)

# Chặn số trang đã-submit-chưa-xong (mọi request cộng lại). Producer acquire
# trước khi submit; khi đủ LLM_CONCURRENCY trang in-flight, vòng render sẽ
# nghẽn lại tại submit_page → không render trước cả nghìn trang rồi giữ ảnh
# base64 trong RAM.
_slots = threading.Semaphore(LLM_CONCURRENCY)

# Gauge số trang đang in-flight — cho endpoint /ocr/stats quan sát.
_inflight = 0
_inflight_lock = threading.Lock()


def inflight() -> int:
    """Số trang OCR đang chạy/chờ trong pool chung (mọi request cộng lại)."""
    with _inflight_lock:
        return _inflight


def _on_done(_: Future) -> None:
    global _inflight
    with _inflight_lock:
        _inflight -= 1
    _slots.release()


def submit_page(fn: Callable[..., object], *args) -> Future:
    """Submit một job OCR-trang vào pool chung.

    BLOCKING khi pool đã đầy LLM_CONCURRENCY trang — chính là backpressure
    mong muốn: caller (vòng render) tự chờ thay vì nhồi thêm việc cho vLLM.
    """
    global _inflight
    _slots.acquire()
    with _inflight_lock:
        _inflight += 1
    try:
        fut = _executor.submit(fn, *args)
    except BaseException:
        with _inflight_lock:
            _inflight -= 1
        _slots.release()
        raise
    fut.add_done_callback(_on_done)
    return fut

# OCR_HVKS — Pipeline OCR & Trích xuất Văn bản Pháp lý

Hệ thống OCR + trích xuất thông tin + xuất PDF cho văn bản tố tụng, cáo trạng, quyết định, bản án tiếng Việt. Dựa trên Qwen-VL (vLLM) để OCR ảnh/PDF, trích xuất 67 trường cố định, và viết lại LaTeX → PDF.

## Kiến trúc tổng quan

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                         UI (ocr_v3.html)                             │
 │   ┌─────────────┐   ┌──────────────────┐   ┌────────────────────┐    │
 │   │ Hàng chờ    │   │ Viewer OCR       │   │ Trích xuất trường  │    │
 │   │ (upload)    │   │ (xem + sửa text) │   │ (4 nhóm × 67 field)│    │
 │   └──────┬──────┘   └────────┬─────────┘   └──────────┬─────────┘    │
 └──────────┼───────────────────┼────────────────────────┼──────────────┘
            │ POST /ocr/stream  │ POST /latex, /pdf      │ POST /extract
            ▼                   ▼                        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │          FastAPI Backend (combined via run_local_src.py)             │
 │   ┌─────────────┐   ┌──────────────────┐   ┌────────────────────┐    │
 │   │ ocr_server  │   │ latex_server     │   │ extract            │    │
 │   │ .py         │   │ .py              │   │ .py                │    │
 │   │ (Qwen-3.6)   │   │ (split per page) │   │ (4 song song)      │    │
 │   └──────┬──────┘   └────────┬─────────┘   └──────────┬─────────┘    │
 └──────────┼───────────────────┼────────────────────────┼──────────────┘
            │                   │                        │
            └───────────────────┴────────────────────────┘
                                │
                                ▼
                         vLLM (Qwen-3.6)
                       kv-cache fp8 · GPU
```

## Các thành phần

### 1. Backend Python ([local/](local/))

| File | Vai trò |
|------|---------|
| [ocr_server.py](local/ocr_server.py) | FastAPI OCR. Nhận PDF/ảnh → tách trang (Poppler) → gọi vLLM Qwen-3.6 cho từng trang song song → trả text. Có stream SSE. |
| [extract.py](local/extract.py) | APIRouter `/extract`. Đọc 4 file [local/extract_md/](local/extract_md/) làm schema trường, chia 4 request song song (mỗi request 1 nhóm), merge theo schema cố định. Trường trống → `""`. |
| [latex_server.py](local/latex_server.py) | FastAPI LaTeX/PDF. Nhận text OCR có marker `--- Trang N ---`, split theo trang, gộp `LATEX_PAGES_PER_CHUNK=4` trang/request, chạy song song (`LATEX_CHUNK_WORKERS=4`). XeLaTeX compile → PDF. |
| [vllm_client.py](local/vllm_client.py) | Wrapper gọi vLLM OpenAI-compat. |
| [config.py](local/config.py) | Env vars: `VLLM_BASE_URL`, `MODEL_NAME`, `OCR_PORT`, `LATEX_PORT`, `MAX_WORKERS`, `DPI`, `POPPLER_PATH`… |

### 2. Colab launcher ([colab/run_local_src.py](colab/run_local_src.py))

Chạy toàn bộ pipeline trên 1 notebook Colab:
- Khởi động vLLM (Qwen3.6-VL, fp8 kv-cache, prefix caching, chunked prefill).
- Build combined FastAPI whitelist: `/ocr`, `/ocr/stream`, `/extract`, `/extract/schema`, `/latex`, `/pdf`, `/compile`, `/latex/stream`.
- Expose tunnel: **Cloudflared** (mặc định, URL random mỗi lần) hoặc **Localtunnel** (subdomain cố định nhưng kém ổn).
- `keepalive_loop`: chặn cell 24h, ping `/health` localhost + tunnel, warmup vLLM 1 token mỗi 10 phút để GPU không bị thu hồi, auto-reconnect tunnel khi rớt.

### 3. UI ([ocr_v3.html](ocr_v3.html))

File HTML tĩnh, mở trực tiếp trong browser. Truyền URL tunnel qua query param:
```
ocr_v3.html?api=https://xxx.trycloudflare.com
```

Tính năng:
- Upload PDF/ảnh nhiều file, chọn file để OCR hàng loạt.
- Xem kết quả OCR theo trang, thumbnail, sao chép, tải `.txt`, tải PDF.
- **Sửa trang**: chỉnh text OCR trực tiếp; thay đổi sẽ được dùng khi trích xuất / xuất PDF.
- **Trích xuất trường**: panel bên phải hiển thị 4 nhóm × 67 field, sao chép JSON nested theo nhóm.
- Tự động reconnect health, không báo "mất kết nối" khi đang xử lý OCR.

## Pipeline dòng chảy dữ liệu

### OCR
1. User upload PDF → UI POST `/ocr/stream` (multipart).
2. Server tách PDF thành ảnh (pdf2image, DPI=300).
3. Mỗi trang → gọi vLLM Qwen-VL song song (`MAX_WORKERS=32`), prompt tiếng Việt chuyên OCR pháp lý.
4. Stream SSE từng trang về UI, UI render + lưu `results[fileKey].pages[i].text`.

### Trích xuất trường
1. User bấm nút "Trích xuất" (không tự động).
2. UI gộp text tất cả trang (dạng `--- Trang N ---\n...`) → POST `/extract` `{"text": "..."}`.
3. Server load sẵn 4 md từ [local/extract_md/](local/extract_md/) (01 Bản án, 02 Bị cáo VN, 03 Bị cáo nước ngoài, 04 Pháp nhân thương mại).
4. `ThreadPoolExecutor(4)` chạy 4 request LLM song song, mỗi request kèm nội dung 1 md.
5. Parse JSON `{"Col N": "value"}`, map về schema cố định → đảm bảo đủ 67 trường, trường không có trả `""`.
6. UI render 4 bảng + tag `đã điền/tổng`.

### Xuất PDF
1. UI bấm "Tải PDF" → POST `/pdf` `{"text": "..."}`.
2. Server `split_ocr_by_page()` chia theo `--- Trang N ---` marker.
3. Gộp `LATEX_PAGES_PER_CHUNK` trang/request, chạy `LATEX_CHUNK_WORKERS` request song song.
4. Chunk thứ 2 trở đi có cờ `is_continuation=True` (LLM không re-emit quốc hiệu/tiêu ngữ).
5. Ghép `latex_body`, wrap preamble XeLaTeX, compile `xelatex → PDF`.
6. Nếu compile fail → tự gọi `repair_latex_body` với error log, compile lần 2.

## Cài đặt & chạy

### Colab Pro+ (khuyến nghị)

```python
# Cell 1: upload local/ và colab/ sang /content/drive/MyDrive/OCR_HVKS/
# rồi:

import sys
sys.path.insert(0, '/content/drive/MyDrive/OCR_HVKS/colab')

import run_local_src
run_local_src.main()
```

Sau ~3-5 phút (cài xelatex + tải model), output in ra URL tunnel:
```
API tunnel (cloudflared): https://xxx-xxx-xxx.trycloudflare.com
```

Copy URL vào UI: `ocr_v3.html?api=https://xxx-xxx-xxx.trycloudflare.com`.

Muốn subdomain cố định (không ổn định bằng):
```python
import os
os.environ['TUNNEL_TYPE'] = 'localtunnel'
os.environ['SUBDOMAIN'] = 'vks-hvks-ocr-your-name'
```

### Local (có GPU)

Xem [README_GPU_SETUP.md](README_GPU_SETUP.md) cho cấu hình DeepDoc + VietOCR offline.

Cho vLLM:
```bash
# Cần vLLM + Qwen3.6-VL weights + xelatex + poppler
pip install -r requirements.txt

# Terminal 1 — vLLM
vllm serve Qwen/Qwen3.6-35B-A3B --port 8008 --kv-cache-dtype fp8_e5m2 ...

# Terminal 2 — OCR API
cd local && python ocr_server.py

# Terminal 3 — LaTeX API
cd local && python latex_server.py
```

Mở `ocr_v3.html?api=http://localhost:8900` (OCR) và set `latex_api=http://localhost:8901` nếu tách port.

## API endpoints

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/ocr` | `multipart/form-data file=<pdf>` | `{pages: [{page, text, time_s, ok}]}` |
| POST | `/ocr/stream` | same | SSE: `start` → `page` × N → `done` |
| POST | `/extract` | `{"text": "..."}` | `{groups: [{id, name, fields: [{col, ten_truong, value}]}]}` |
| GET  | `/extract/schema` | — | Schema 4 nhóm + field list (không gọi LLM) |
| POST | `/latex` | `{"text": "..."}` | `{latex_body, full_document, time_s, debug_id}` |
| POST | `/pdf` | `{"text": "..."}` | PDF binary |
| POST | `/compile` | `{"latex": "...", "full_document": bool}` | PDF binary |
| GET  | `/health` | — | `{status, vllm, xelatex, model_name, ...}` |

## Biến môi trường chính

| Var | Default | Mô tả |
|-----|---------|-------|
| `MODEL_NAME` | `Qwen/Qwen3.6-35B-A3B` | Model vLLM |
| `VLLM_BASE_URL` | `http://localhost:8008` | vLLM URL |
| `OCR_PORT` | `8900` | FastAPI OCR |
| `LATEX_PORT` | `8901` | FastAPI LaTeX |
| `MAX_WORKERS` | `32` | OCR workers (song song trang) |
| `DPI` | `300` | PDF → image DPI |
| `LATEX_PAGES_PER_CHUNK` | `4` | Trang/request LaTeX |
| `LATEX_CHUNK_WORKERS` | `4` | Request LaTeX song song |
| `POPPLER_PATH` | `""` | Path pdfinfo nếu không trong PATH (Windows) |
| `TUNNEL_TYPE` | `cloudflared` | `cloudflared` hoặc `localtunnel` |
| `SUBDOMAIN` | `vks-hvks-ocr-extract` | Chỉ localtunnel |
| `GPU_MEMORY_UTILIZATION` | `0.9` | vLLM GPU util |
| `MAX_MODEL_LEN` | `100000` | Context length vLLM |

## Trường trích xuất

4 nhóm field trong [local/extract_md/](local/extract_md/):

| File | Nhóm | Phạm vi | Số field |
|------|------|---------|----------|
| `01_BanAn_QuyetDinh.md` | Bản án / Quyết định | Col 0–19 | 20 |
| `02_ThongTin_BiCao.md` | Bị cáo công dân VN | Col 20–49 | 30 |
| `03_ThongTin_BiCao_NuocNgoai.md` | Bị cáo nước ngoài | Col 50–56 | 7 |
| `04_PhapNhan_ThuongMai.md` | Pháp nhân thương mại | Col 57–66 | 10 |

Mỗi md là bảng markdown `| STT | Mã trường | Tên trường | Col | Ghi chú |`. Server parse bảng lúc startup → ép schema cố định cho mọi response.

## Troubleshooting

**Tunnel 503 Tunnel Unavailable**
- Cloudflared: chờ keepalive reconnect (~4 phút) hoặc chạy lại `run_local_src.start_cloudflared_tunnel()`.
- Localtunnel: subdomain có thể bị chiếm; đổi `SUBDOMAIN` hoặc chờ ~5 phút để lease cũ hết.

**UI báo "Không kết nối được" giữa chừng**
- Health timeout 30s + cần 3 fail liên tiếp mới báo. Nếu đang OCR thì không bao giờ hạ status → error. Nếu báo liên tục: check tunnel tại bước trên.

**LaTeX bị cắt, PDF thiếu trang cuối**
- `LATEX_PAGES_PER_CHUNK=4` với `max_tokens=16384` thường đủ. Nếu gặp `finish_reason=length` trong log, giảm `LATEX_PAGES_PER_CHUNK=2`.

**Colab ngắt session khi chạy vLLM**
- Pro+ cần `keepalive_loop` block cell (đã tích hợp). Không đóng tab ngay sau start, để keepalive in vài log đầu tiên.
- Compute unit cạn: kiểm tra `Runtime → Xem tài nguyên`.

**Endpoint mới trên Colab 404**
- Nhớ thêm path vào whitelist `add_routes(...)` trong [colab/run_local_src.py](colab/run_local_src.py).

## Cấu trúc repo

```
OCR_HVKS/
├── local/                    # Backend Python (FastAPI + logic)
│   ├── ocr_server.py
│   ├── latex_server.py
│   ├── extract.py            # /extract router
│   ├── extract_md/           # 4 file schema field
│   ├── vllm_client.py
│   └── config.py
├── colab/
│   └── run_local_src.py      # Combined launcher cho Colab
├── deepdoc_vietocr/          # OCR offline (alternative, không dùng vLLM)
├── ocr_v3.html               # UI SPA
├── requirements.txt
├── README.md
└── README_GPU_SETUP.md       # DeepDoc/VietOCR GPU setup
```

# before pull

### git lfs install

### git clone https://github.com/NguyenTienAnh8365/OCR_HVKS.git

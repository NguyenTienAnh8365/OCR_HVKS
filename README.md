# OCR_HVKS — Pipeline OCR & Trích xuất Văn bản Pháp lý

Hệ thống OCR + trích xuất 67 trường + xuất PDF (LaTeX) cho văn bản tố tụng,
cáo trạng, quyết định, bản án tiếng Việt. Dùng Qwen3.6-35B-A3B trên **vLLM**
làm LLM backend, FastAPI làm orchestration, UI tĩnh HTML.

## Kiến trúc

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                           UI (ui/ocr_v3.html)                        │
 │   ┌─────────────┐   ┌──────────────────┐   ┌────────────────────┐    │
 │   │ Hàng chờ    │   │ Viewer OCR       │   │ Trích xuất trường  │    │
 │   │ (upload)    │   │ (xem + sửa text) │   │ (4 nhóm × 67 field)│    │
 │   └──────┬──────┘   └────────┬─────────┘   └──────────┬─────────┘    │
 └──────────┼───────────────────┼────────────────────────┼──────────────┘
            │ POST /ocr/stream  │ POST /latex, /pdf      │ POST /extract
            ▼                   ▼                        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │           FastAPI combined (ocr_hvks.api.app, port 8900)             │
 │   ┌─────────────┐   ┌──────────────────┐   ┌────────────────────┐    │
 │   │ ocr router  │   │ latex router     │   │ extract router     │    │
 │   │ pipeline.py │   │ service.py       │   │ service.py         │    │
 │   └──────┬──────┘   └────────┬─────────┘   └──────────┬─────────┘    │
 └──────────┼───────────────────┼────────────────────────┼──────────────┘
            └───────────────────┴────────────────────────┘
                                │ ocr_hvks.llm.client (HTTP OpenAI-compat)
                                ▼
                     vLLM server (Qwen3.6-35B-A3B, TP=2)
                       fp8 KV-cache · 2× RTX PRO 6000
```

## Cấu trúc repo

```
OCR_HVKS/
├── src/ocr_hvks/
│   ├── config.py                # Env + paths
│   ├── server.py                # uvicorn entrypoint
│   ├── llm/
│   │   └── client.py            # HTTP client → OpenAI-compatible /v1/chat/completions
│   ├── ocr/
│   │   ├── router.py            # /ocr, /ocr/stream
│   │   ├── pipeline.py          # encode + ocr_one_page
│   │   ├── pdf_loader.py        # poppler/pdf2image
│   │   └── prompts.py           # OCR prompt Qwen-VL
│   ├── extract/
│   │   ├── router.py            # /extract, /extract/schema
│   │   ├── service.py           # parse md + LLM song song 4 nhóm
│   │   └── schemas/             # 01_BanAn / 02_BiCao / 03_NuocNgoai / 04_PhapNhan
│   ├── latex/
│   │   ├── router.py            # /latex /pdf /compile /latex/stream /debug
│   │   ├── service.py           # generate_latex_body chunked song song
│   │   ├── normalize.py         # split page marker + cleanup
│   │   ├── compile.py           # xelatex subprocess + debug
│   │   ├── templates.py         # LATEX_PREAMBLE/POSTAMBLE
│   │   └── prompts.py           # SYSTEM_PROMPT + LATEX_EXAMPLE
│   └── api/
│       └── app.py               # FastAPI gắn 3 router + /health tổng
│
├── deploy/
│   ├── install_server.sh        # apt + venv + pip install
│   ├── start_vllm.sh            # khởi động vLLM TP=2
│   ├── start_api.sh             # khởi động uvicorn
│   ├── start_cloudflared.sh     # quick tunnel ra trycloudflare.com
│   └── systemd/                 # 3 unit file: vllm / api / tunnel
│
├── ui/
│   └── ocr_v3.html              # SPA tĩnh
│
├── docs/
│   ├── GPU_SETUP.md             # DeepDoc + VietOCR offline (alternative)
│   └── ocr_pipeline_v2.svg
│
├── third_party/
│   └── deepdoc_vietocr/         # OCR offline thay thế (không dùng LLM backend)
│
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

## Cài đặt trên server

Test trên Ubuntu 22.04+ với 2× NVIDIA RTX PRO 6000 Blackwell.

```bash
# 1. clone
git clone <repo> ~/AI_project/OCR_HVKS && cd ~/AI_project/OCR_HVKS

# 2. tạo venv và cài deps
uv venv .venv --python 3.12.10
source .venv/bin/activate
uv pip install -r requirements.txt && uv pip install -e .

# 3. cài vLLM (pin version ổn định cho Blackwell)
uv pip install vllm==0.19.1

# 4. cài cloudflared
sudo curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# 5. cấu hình
cp .env.example .env
nano .env                        # đổi MODEL_NAME, TP_SIZE nếu cần

# 6. test thủ công (2 terminal)
./deploy/start_vllm.sh           # terminal 1 — đợi server ready
./deploy/start_api.sh            # terminal 2

# 7. health check
curl http://localhost:8900/health

# 8. expose ra ngoài (optional)
./deploy/start_cloudflared.sh    # in URL https://xxx.trycloudflare.com
```

Cho production 24/7 dùng systemd: xem [deploy/systemd/README.md](deploy/systemd/README.md).

## UI

Mở `ui/ocr_v3.html` trực tiếp trong browser, truyền URL API qua query param:

```
ui/ocr_v3.html?api=http://localhost:8900
ui/ocr_v3.html?api=https://xxx-xxx-xxx.trycloudflare.com
```

## API endpoints

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/ocr` | `multipart/form-data file=<pdf>` | `{pages: [{page, text, time_s, ok}]}` |
| POST | `/ocr/stream` | same | SSE: `start` → `page` × N → `done` |
| POST | `/extract` | `{"text": "..."}` | `{groups: [{id, name, fields: [...]}]}` |
| GET  | `/extract/schema` | — | Schema 4 nhóm + field list |
| POST | `/latex` | `{"text": "..."}` | `{latex_body, full_document, time_s, debug_id}` |
| POST | `/pdf` | `{"text": "..."}` | PDF binary |
| POST | `/compile` | `{"latex": "...", "full_document": bool}` | PDF binary |
| GET  | `/debug/{debug_id}` | — | Tất cả file debug LaTeX |
| POST | `/latex/stream` | `{"text": "..."}` | SSE delta tokens |
| GET  | `/health` | — | `{status, llm, xelatex, model_name, ocr, latex}` |

## Pipeline dòng chảy dữ liệu

### OCR
1. UI POST `/ocr/stream` (multipart).
2. `pdf_loader.load_images_from_bytes` tách PDF → ảnh (poppler, DPI=300).
3. `ocr_one_page` chạy song song `MAX_WORKERS` trang → vLLM OpenAI-compatible.
4. Stream SSE từng trang về UI.

### Trích xuất trường
1. UI gộp text tất cả trang (`--- Trang N ---\n...`) → POST `/extract`.
2. `extract.service` load 4 md schema lúc import.
3. `ThreadPoolExecutor(4)` chạy 4 LLM call song song, mỗi call = 1 nhóm.
4. Parse JSON `{"Col N": "value"}` → ép schema cố định 67 trường.

### Xuất PDF
1. UI POST `/pdf` `{"text": "..."}`.
2. `latex.normalize.split_ocr_by_page` chia theo `--- Trang N ---`.
3. Gộp `LATEX_PAGES_PER_CHUNK` trang/request, song song `LATEX_CHUNK_WORKERS`.
4. Chunk thứ 2+ có `is_continuation=True` (LLM không lặp quốc hiệu).
5. Ghép body, wrap preamble, compile `xelatex`.
6. Compile fail → `repair_latex_body` với error log, compile lần 2.

## Biến môi trường chính

Xem [.env.example](.env.example) cho danh sách đầy đủ. Các biến quan trọng:

| Var | Default | Mô tả |
|-----|---------|-------|
| `MODEL_NAME` | `Qwen/Qwen3.6-35B-A3B` | Model vLLM phục vụ |
| `LLM_BASE_URL` | `http://localhost:8008` | URL vLLM (OpenAI-compatible) |
| `API_PORT` | `8900` | FastAPI combined |
| `TP_SIZE` | `2` | Tensor parallel cho vLLM |
| `GPU_MEMORY_UTILIZATION` | `0.90` | GPU memory utilization cho vLLM |
| `MAX_MODEL_LEN` | `100000` | Context length |
| `MAX_WORKERS` | `32` | OCR song song (trang) |
| `LATEX_PAGES_PER_CHUNK` | `4` | Trang/request LaTeX |
| `LATEX_CHUNK_WORKERS` | `4` | Request LaTeX song song |
| `POPPLER_PATH` | `""` | Path bin Poppler (Windows dev) |

## Trường trích xuất

4 file md trong [src/ocr_hvks/extract/schemas/](src/ocr_hvks/extract/schemas/):

| File | Nhóm | Phạm vi | Số field |
|------|------|---------|----------|
| `01_BanAn_QuyetDinh.md` | Bản án / Quyết định | Col 0–19 | 20 |
| `02_ThongTin_BiCao.md` | Bị cáo công dân VN | Col 20–49 | 30 |
| `03_ThongTin_BiCao_NuocNgoai.md` | Bị cáo nước ngoài | Col 50–56 | 7 |
| `04_PhapNhan_ThuongMai.md` | Pháp nhân thương mại | Col 57–66 | 10 |

Mỗi md là bảng markdown `| STT | Mã trường | Tên trường | Col | Ghi chú |`.
Server parse lúc startup → ép schema cố định cho mọi response.

## Troubleshooting

**vLLM không khởi động được**
- Kiểm tra `nvidia-smi` đảm bảo 2 GPU còn trống.
- Hạ `GPU_MEMORY_UTILIZATION=0.85` nếu OOM.
- `CUDA_VISIBLE_DEVICES=0,1` đúng index GPU.
- Xem log: `journalctl -u vllm@$USER.service -f`.

**Tunnel cloudflared 503**
- Chờ ~4 phút để cloudflared reconnect, hoặc restart `ocr-hvks-tunnel@$USER.service`.
- URL random mỗi lần khởi động — copy lại từ log mới.

**LaTeX cắt trang cuối**
- `LATEX_PAGES_PER_CHUNK=4` với `max_tokens=16384` thường đủ.
- Nếu log có `finish_reason=length` → giảm `LATEX_PAGES_PER_CHUNK=2`.

**Endpoint 404**
- Tất cả router gắn trong [src/ocr_hvks/api/app.py](src/ocr_hvks/api/app.py). Thêm endpoint mới chỉ cần `include_router` nếu là router mới.

## Dev local trên Windows

Vẫn chạy được. Cần MiKTeX + Poppler (winget):

```powershell
winget install MiKTeX.MiKTeX
winget install oschwartz10612.Poppler
```

Set `POPPLER_PATH` trong `.env` trỏ tới bin của Poppler. Chạy:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
# vLLM trên Linux/CUDA — ở Windows có thể dùng tunnel ngược tới vLLM trên server
$env:LLM_BASE_URL = "https://xxx.trycloudflare.com"
ocr-hvks-server
```

# run product
## Cài unit files (1 lần)
```bash
sudo cp deploy/systemd/vllm.service            /etc/systemd/system/vllm@.service
sudo cp deploy/systemd/ocr-hvks-api.service    /etc/systemd/system/ocr-hvks-api@.service
sudo cp deploy/systemd/ocr-hvks-tunnel.service /etc/systemd/system/ocr-hvks-tunnel@.service
sudo systemctl daemon-reload
```

## Start
```bash
sudo systemctl enable --now vllm@abc.service
sudo systemctl enable --now ocr-hvks-api@abc.service
sudo systemctl enable --now ocr-hvks-tunnel@abc.service
```

## Xem log
```bash
sudo journalctl -u vllm@abc.service -f
sudo journalctl -u ocr-hvks-api@abc.service -f
sudo journalctl -u ocr-hvks-tunnel@abc.service -f
```

## Restart / Stop
```bash
sudo systemctl restart vllm@abc.service
sudo systemctl restart ocr-hvks-api@abc.service
sudo systemctl stop vllm@abc.service
```

## Health check
```bash
curl http://localhost:8900/health
```

## Lấy URL tunnel
```bash
sudo journalctl -u ocr-hvks-tunnel@abc.service -f | grep trycloudflare
```

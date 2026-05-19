# systemd units cho OCR_HVKS

Deploy 3 service: vLLM (LLM backend) → FastAPI (combined) → Cloudflared tunnel.
Unit là template (`@`), `%i` thay bằng tên user chạy — ví dụ dưới dùng `abc`.

Repo đặt tại `~/AI_project/OCR_HVKS` (unit file trỏ tới `/home/%i/AI_project/OCR_HVKS`).

## Cài unit files (1 lần)

```bash
sudo cp deploy/systemd/vllm.service            /etc/systemd/system/vllm@.service
sudo cp deploy/systemd/ocr-hvks-api.service    /etc/systemd/system/ocr-hvks-api@.service
sudo cp deploy/systemd/ocr-hvks-tunnel.service /etc/systemd/system/ocr-hvks-tunnel@.service
sudo systemctl daemon-reload
```

> Mỗi lần sửa file `.service` trong repo phải `cp` lại + `daemon-reload` mới có hiệu lực.

## Start

`enable --now` = chạy ngay + tự lên khi boot.

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

- Sửa code `client.py` / `router.py` / `config.py` → `restart ocr-hvks-api@abc`.
- Sửa `MAX_NUM_SEQS` / config vLLM → `restart vllm@abc`.

## Health check

```bash
curl http://localhost:8900/health
```

## Lấy URL tunnel

```bash
sudo journalctl -u ocr-hvks-tunnel@abc.service -f | grep trycloudflare
```

URL random mỗi lần tunnel khởi động lại — lấy lại từ log.

## Uninstall

```bash
sudo systemctl disable --now ocr-hvks-tunnel@abc.service ocr-hvks-api@abc.service vllm@abc.service
sudo rm /etc/systemd/system/{vllm,ocr-hvks-api,ocr-hvks-tunnel}@.service
sudo systemctl daemon-reload
```

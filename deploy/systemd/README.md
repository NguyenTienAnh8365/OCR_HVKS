# systemd units cho OCR_HVKS

Deploy 3 service: vLLM (LLM backend) → FastAPI (combined) → Cloudflared tunnel.

## Cài đặt

Giả sử repo nằm ở `/opt/ocr_hvks` và user chạy là `abc` (đổi nếu khác).

```bash
# 1. Đặt repo + cài deps
sudo mkdir -p /opt/ocr_hvks
sudo chown $USER:$USER /opt/ocr_hvks
git clone <repo> /opt/ocr_hvks
cd /opt/ocr_hvks
./deploy/install_server.sh           # cài apt deps + venv + pip install

# 2. Cài vLLM trong venv (theo CUDA của server)
. .venv/bin/activate
pip install vllm                     # hoặc theo docs.vllm.ai cho CUDA tương ứng

# 3. Cấu hình env
cp .env.example .env
nano .env                            # đổi MODEL_NAME, TP_SIZE, ports nếu cần

# 4. Cài systemd unit (template — %i sẽ thay bằng tên user)
sudo cp deploy/systemd/vllm.service            /etc/systemd/system/vllm@.service
sudo cp deploy/systemd/ocr-hvks-api.service    /etc/systemd/system/ocr-hvks-api@.service
sudo cp deploy/systemd/ocr-hvks-tunnel.service /etc/systemd/system/ocr-hvks-tunnel@.service
sudo systemctl daemon-reload

# 5. Start theo user (vd user `abc`)
sudo systemctl enable --now vllm@abc.service
sudo systemctl enable --now ocr-hvks-api@abc.service
sudo systemctl enable --now ocr-hvks-tunnel@abc.service
```

## Quan sát

```bash
sudo systemctl status vllm@abc.service
sudo journalctl -u vllm@abc.service -f
sudo journalctl -u ocr-hvks-api@abc.service -f
sudo journalctl -u ocr-hvks-tunnel@abc.service -f | grep trycloudflare
```

## Uninstall

```bash
sudo systemctl disable --now ocr-hvks-tunnel@abc.service ocr-hvks-api@abc.service vllm@abc.service
sudo rm /etc/systemd/system/{vllm,ocr-hvks-api,ocr-hvks-tunnel}@.service
sudo systemctl daemon-reload
```

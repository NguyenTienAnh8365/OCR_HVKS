"""
vLLM server cho Colab — chỉ load model và expose port 8008 qua localtunnel.
Toàn bộ pipeline OCR/LaTeX/PDF chạy ở máy local, gọi HTTP sang đây.

Cách dùng trên Colab (paste lần lượt vào 3 cell):

# ========== Cell 1: cài đặt ==========
!pip uninstall -q vllm -y
!pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
!pip install -q vllm --extra-index-url https://wheels.vllm.ai/nightly

# ========== Cell 2: chạy file này ==========
!wget -q -O vllm_server.py <URL_TO_THIS_FILE>   # hoặc upload tay
import vllm_server
vllm_server.main()

# ========== Cell 3: keep-alive ==========
from IPython.display import display, Javascript
display(Javascript(r'''
(function(){
  if (window.__vllmKeepAlive) return;
  window.__vllmKeepAlive = true;
  setInterval(function(){
    try {
      document.querySelectorAll('colab-connect-button').forEach(b => {
        const s = b.shadowRoot;
        if (s) { const btn = s.querySelector('#connect'); if (btn) btn.click(); }
      });
      document.dispatchEvent(new MouseEvent('mousemove', {clientX:1, clientY:1, bubbles:true}));
    } catch(e){}
  }, 45*1000);
})();
'''))
"""

import os
import re
import time
import subprocess
import threading


MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen3.6-35B-A3B")
VLLM_PORT = int(os.environ.get("VLLM_PORT", 8008))
SUBDOMAIN = os.environ.get("SUBDOMAIN", "vks-ocr-hvks")
FIXED_URL = f"https://{SUBDOMAIN}.loca.lt"


def start_vllm():
    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--port", str(VLLM_PORT),
        "--host", "0.0.0.0",
        "--gpu-memory-utilization", "0.9",
        "--kv-cache-dtype", "fp8_e5m2",
        "--dtype", "bfloat16",
        "--max-model-len", "32768",
        "--max-num-seqs", "64",
        "--max-num-batched-tokens", "16384",
        "--enable-prefix-caching",
        "--enable-chunked-prefill",
        "--trust-remote-code",
    ]

    def _run():
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            print(line, end="")

    threading.Thread(target=_run, daemon=True).start()


def wait_for_vllm(timeout=300):
    import requests
    url = f"http://localhost:{VLLM_PORT}/v1/models"
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def install_localtunnel():
    if subprocess.run("which lt", shell=True, capture_output=True).returncode == 0:
        return
    subprocess.run("npm install -g localtunnel -q", shell=True, timeout=120)


def start_tunnel():
    log_file = "tunnel_vllm.log"
    subprocess.run("pkill -9 -f 'lt --port' || true", shell=True, timeout=5)
    time.sleep(2)
    try:
        os.remove(log_file)
    except FileNotFoundError:
        pass

    subprocess.Popen(
        f"lt --port {VLLM_PORT} --subdomain {SUBDOMAIN} > {log_file} 2>&1 &",
        shell=True,
    )

    for _ in range(40):
        time.sleep(1)
        try:
            with open(log_file) as f:
                log = f.read()
            m = re.search(r"https://[\w-]+\.loca\.lt", log)
            if m:
                return m.group(0)
        except FileNotFoundError:
            pass
    return None


def main():
    print(f"[1/4] start vLLM on port {VLLM_PORT} (model={MODEL_NAME}) ...", flush=True)
    start_vllm()

    print("[2/4] wait for vLLM to become ready ...", flush=True)
    if not wait_for_vllm():
        print("❌ vLLM không khởi động được trong 5 phút.")
        return
    print("      ✅ vLLM ready")

    print("[3/4] install localtunnel if missing ...", flush=True)
    install_localtunnel()

    print(f"[4/4] expose tunnel subdomain={SUBDOMAIN} ...", flush=True)
    url = None
    for attempt in range(1, 4):
        url = start_tunnel()
        if url == FIXED_URL:
            break
        print(f"      attempt {attempt}/3 got {url!r}, retry ...", flush=True)

    if not url:
        print(f"❌ Không chiếm được subdomain '{SUBDOMAIN}'. Đổi SUBDOMAIN rồi thử lại.")
        return

    try:
        import requests
        pw = requests.get("https://loca.lt/mytunnelpassword", timeout=10).text.strip()
    except Exception:
        pw = "<lấy tay tại https://loca.lt/mytunnelpassword>"

    print("\n" + "=" * 60)
    print(f"✅ vLLM tunnel: {url}")
    print(f"🔑 Tunnel password (IP Colab): {pw}")
    print(f"📋 Endpoint OpenAI-compatible:")
    print(f"   GET  {url}/v1/models")
    print(f"   POST {url}/v1/chat/completions")
    print("=" * 60)
    print("\n→ Trên máy local, đặt VLLM_BASE_URL=<url> trong local/.env rồi chạy:")
    print("   python ocr_server.py")
    print("   python latex_server.py")


if __name__ == "__main__":
    main()

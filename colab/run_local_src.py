"""
Run the source files from /content/local on Colab.

Workflow on Colab:
1. Upload the whole `local/` folder from this repo to `/content/local`
2. Upload this file to `/content/run_local_src.py`
3. Install deps and system packages
4. Run:

   import run_local_src
   run_local_src.main()

Then open local UI with:
   ocr_v3.html?api=https://<your-subdomain>.loca.lt

This launcher reuses:
  - /content/local/ocr_server.py
  - /content/local/latex_server.py
  - /content/local/config.py
  - /content/local/vllm_client.py
"""

import os
import re
import sys
import time
import subprocess
import threading
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute


LOCAL_SRC = Path(os.environ.get("LOCAL_SRC", "/content/drive/MyDrive/OCR_HVKS/local"))
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen3.6-35B-A3B")
VLLM_PORT = int(os.environ.get("VLLM_PORT", 8008))
COMBINED_API_PORT = int(os.environ.get("COMBINED_API_PORT", os.environ.get("API_PORT", 8900)))
SUBDOMAIN = os.environ.get("SUBDOMAIN", "vks-hvks-ocr")
FIXED_URL = f"https://{SUBDOMAIN}.loca.lt"
GPU_MEMORY_UTILIZATION = float(os.environ.get("GPU_MEMORY_UTILIZATION", "0.9"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "100000"))
MAX_NUM_SEQS = int(os.environ.get("MAX_NUM_SEQS", "64"))
MAX_NUM_BATCHED_TOKENS = int(os.environ.get("MAX_NUM_BATCHED_TOKENS", "24000"))

# Ensure imported local/config.py points to the Colab-local services even if
# the uploaded folder contains a machine-specific .env from Windows.
os.environ.setdefault("VLLM_BASE_URL", f"http://localhost:{VLLM_PORT}")
os.environ.setdefault("OCR_PORT", "8900")
os.environ.setdefault("LATEX_PORT", "8901")
os.environ.setdefault("DEBUG_DIR", "/content/debug_latex")
os.environ["POPPLER_PATH"] = ""


def require_local_src():
    required = [
        LOCAL_SRC / "config.py",
        LOCAL_SRC / "vllm_client.py",
        LOCAL_SRC / "ocr_server.py",
        LOCAL_SRC / "latex_server.py",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing uploaded local source files:\n" + "\n".join(missing))


require_local_src()
sys.path.insert(0, str(LOCAL_SRC))

import ocr_server  # noqa: E402
import latex_server  # noqa: E402


def cleanup_existing_processes():
    for cmd in (
        "pkill -9 -f 'vllm serve' || true",
        f"fuser -k {VLLM_PORT}/tcp || true",
        f"fuser -k {COMBINED_API_PORT}/tcp || true",
    ):
        try:
            subprocess.run(cmd, shell=True, timeout=10)
        except Exception:
            pass
    time.sleep(2)


def start_vllm():
    child_env = os.environ.copy()
    # These are app-level env vars, not vLLM env vars. Remove them from the
    # child process to avoid warnings and accidental behavior changes.
    child_env.pop("VLLM_BASE_URL", None)
    # If this override was left around in a notebook cell, it can force a bad
    # KV-cache layout. Let vLLM profile the cache itself unless the user sets it intentionally.
    child_env.pop("VLLM_NUM_GPU_BLOCKS_OVERRIDE", None)

    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--port", str(VLLM_PORT),
        "--host", "0.0.0.0",
        "--gpu-memory-utilization", str(GPU_MEMORY_UTILIZATION),
        "--kv-cache-dtype", "fp8_e5m2",
        "--dtype", "bfloat16",
        "--max-model-len", str(MAX_MODEL_LEN),
        "--max-num-seqs", str(MAX_NUM_SEQS),
        "--max-num-batched-tokens", str(MAX_NUM_BATCHED_TOKENS),
        "--enable-prefix-caching",
        "--enable-chunked-prefill",
        "--trust-remote-code",
    ]

    def _run():
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=child_env,
        )
        for line in proc.stdout:
            print(line, end="")

    threading.Thread(target=_run, daemon=True, name="vllm-colab").start()


def wait_for_vllm(timeout=300):
    url = f"http://localhost:{VLLM_PORT}/v1/models"
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if requests.get(url, timeout=5).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def install_localtunnel():
    if subprocess.run("which lt", shell=True, capture_output=True).returncode == 0:
        return
    subprocess.run("npm install -g localtunnel -q", shell=True, timeout=120)


def install_tex_and_fonts():
    """Cài xelatex + poppler + fonts (DejaVu) nếu thiếu. Chỉ chạy trên Linux Colab."""
    if subprocess.run("which xelatex", shell=True, capture_output=True).returncode == 0 \
            and subprocess.run("which pdftoppm", shell=True, capture_output=True).returncode == 0:
        return
    print("      installing texlive-xetex + poppler + MS Core Fonts (Times New Roman, Arial, Courier New) (~3-5 phút) ...", flush=True)
    subprocess.run(
        "echo 'ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true' "
        "| debconf-set-selections && "
        "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
        "texlive-xetex texlive-latex-extra texlive-fonts-extra texlive-lang-vietnamese "
        "poppler-utils ttf-mscorefonts-installer && fc-cache -f",
        shell=True, timeout=600,
    )


def start_tunnel():
    log_file = "tunnel_api.log"
    subprocess.run("pkill -9 -f 'lt --port' || true", shell=True, timeout=5)
    time.sleep(2)
    try:
        os.remove(log_file)
    except FileNotFoundError:
        pass

    subprocess.Popen(
        f"lt --port {COMBINED_API_PORT} --subdomain {SUBDOMAIN} > {log_file} 2>&1 &",
        shell=True,
    )

    for _ in range(40):
        time.sleep(1)
        try:
            with open(log_file, encoding="utf-8", errors="ignore") as f:
                log = f.read()
            m = re.search(r"https://[\w-]+\.loca\.lt", log)
            if m:
                return m.group(0)
        except FileNotFoundError:
            pass
    return None


def build_app():
    app = FastAPI(title="HVKS API (local src on Colab)", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def add_routes(source_app, allowed_paths):
        for route in source_app.router.routes:
            if isinstance(route, APIRoute) and route.path in allowed_paths:
                app.router.routes.append(route)

    add_routes(ocr_server.app, {"/ocr", "/ocr/stream"})
    add_routes(latex_server.app, {"/latex", "/pdf", "/compile", "/debug/{debug_id}", "/latex/stream"})

    @app.get("/health")
    def combined_health():
        ocr = ocr_server.health()
        latex = latex_server.health()
        return {
            "status": "ok",
            "ocr": ocr,
            "latex": latex,
            "vllm": "ready" if ocr.get("vllm") == "ready" and latex.get("vllm") == "ready" else "unreachable",
            "xelatex": bool(latex.get("xelatex")),
            "model_name": latex.get("model_name") or ocr.get("model_name"),
        }

    return app


def run_api():
    uvicorn.run(build_app(), host="0.0.0.0", port=COMBINED_API_PORT, log_level="warning")


def main():
    print(f"[1/5] using uploaded source from {LOCAL_SRC}", flush=True)
    print(
        f"      model={MODEL_NAME} vllm_port={VLLM_PORT} combined_api_port={COMBINED_API_PORT} gpu_mem_util={GPU_MEMORY_UTILIZATION}",
        flush=True,
    )
    print(
        f"      max_model_len={MAX_MODEL_LEN} max_num_seqs={MAX_NUM_SEQS} max_num_batched_tokens={MAX_NUM_BATCHED_TOKENS}",
        flush=True,
    )

    print("[2/6] cleanup old vLLM/API processes ...", flush=True)
    cleanup_existing_processes()

    print("[3/6] install texlive/poppler/fonts if missing ...", flush=True)
    install_tex_and_fonts()

    print(f"[4/6] start vLLM on port {VLLM_PORT} ...", flush=True)
    start_vllm()
    if not wait_for_vllm():
        print(
            "ERROR: vLLM did not become ready within 5 minutes. "
            "Try lower GPU_MEMORY_UTILIZATION, for example 0.2.",
            flush=True,
        )
        return
    print("      vLLM ready", flush=True)

    print(f"[5/6] start combined OCR + LaTeX API on port {COMBINED_API_PORT} ...", flush=True)
    threading.Thread(target=run_api, daemon=True, name="api-colab").start()
    time.sleep(6)
    try:
        r = requests.get(f"http://localhost:{COMBINED_API_PORT}/health", timeout=5)
        print("      health:", r.status_code, r.text[:300], flush=True)
    except Exception as e:
        print("      health failed:", e, flush=True)

    print("[6/6] install localtunnel if missing ...", flush=True)
    install_localtunnel()

    print(f"[tunnel] expose API tunnel subdomain={SUBDOMAIN} ...", flush=True)
    url = None
    for attempt in range(1, 4):
        url = start_tunnel()
        if url == FIXED_URL:
            break
        print(f"      attempt {attempt}/3 got {url!r}, retry ...", flush=True)

    if not url:
        print(f"ERROR: cannot reserve subdomain '{SUBDOMAIN}'. Change SUBDOMAIN and try again.")
        return

    try:
        pw = requests.get("https://loca.lt/mytunnelpassword", timeout=10).text.strip()
    except Exception:
        pw = "<fetch manually from https://loca.lt/mytunnelpassword>"

    print("\n" + "=" * 60)
    print(f"API tunnel: {url}")
    print(f"Tunnel password: {pw}")
    print("Endpoints:")
    print(f"  GET  {url}/health")
    print(f"  POST {url}/ocr")
    print(f"  POST {url}/ocr/stream")
    print(f"  POST {url}/latex")
    print(f"  POST {url}/pdf")
    print(f"  POST {url}/compile")
    print(f"  POST {url}/latex/stream")
    print("=" * 60)
    print(f"\nOpen local UI with: ocr_v3.html?api={url}")


if __name__ == "__main__":
    main()

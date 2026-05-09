#!/usr/bin/env bash
# Cài đặt dependencies trên Ubuntu/Debian server (chạy 1 lần khi setup).
# - texlive-xetex + fonts cho LaTeX/PDF
# - poppler-utils cho pdf2image
# - cloudflared cho tunnel
# - Python deps trong virtualenv

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"

echo "[install] apt packages: poppler, texlive-xetex, fonts, build deps ..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3-venv python3-pip \
  poppler-utils \
  texlive-xetex texlive-latex-extra texlive-fonts-extra texlive-lang-vietnamese \
  fonts-dejavu fonts-dejavu-extra \
  curl wget ca-certificates

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[install] cloudflared ..."
  sudo curl -fsSL \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared
  sudo chmod +x /usr/local/bin/cloudflared
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[install] python venv at ${VENV_DIR} ..."
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
. "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel
pip install -r "${REPO_ROOT}/requirements.txt"
pip install -e "${REPO_ROOT}"

echo
echo "[install] DONE. Bước tiếp theo:"
echo "  1) Cài SGLang riêng (theo CUDA version trên server):"
echo "       pip install --upgrade pip"
echo "       pip install \"sglang[all]\""
echo "     (xem https://docs.sglang.ai/start/install.html)"
echo "  2) Copy .env.example → .env và chỉnh."
echo "  3) Test:  ./deploy/start_sglang.sh   và   ./deploy/start_api.sh"
echo "  4) Production: cài systemd units trong deploy/systemd/"

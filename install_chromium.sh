#!/usr/bin/env bash
# ==========================================================
# install_chromium.sh — Render prebuild cache + Chromium fetch
# ==========================================================

set -e

echo "[INFO] === Prebuild: Checking cached Chromium ==="

CHROMIUM_DIR="/opt/render/.local/share/pyppeteer/local-chromium"
CHROMIUM_EXEC="$CHROMIUM_DIR/1181205/chrome-linux/chrome"

# --- Ensure pyppeteer exists before trying to use it ---
echo "[INFO] Ensuring pyppeteer is available..."
pip install --quiet pyppeteer

if [ -x "$CHROMIUM_EXEC" ]; then
  echo "[INFO] Cached Chromium found at: $CHROMIUM_EXEC"
  "$CHROMIUM_EXEC" --version || echo "[WARN] Could not read Chromium version."
else
  echo "[WARN] No cached Chromium detected. Triggering pyppeteer download..."
  mkdir -p "$CHROMIUM_DIR"

  python3 - <<'PYCODE'
from pyppeteer import chromium_downloader

try:
    path = chromium_downloader.chromium_executable()
    print(f"[INFO] Chromium already available at {path}")
except Exception:
    print("[INFO] Downloading Chromium for pyppeteer...")
    chromium_downloader.download_chromium()
    path = chromium_downloader.chromium_executable()
    print(f"[INFO] Chromium downloaded to: {path}")
PYCODE
fi

echo "[INFO] === Chromium prebuild step complete ==="

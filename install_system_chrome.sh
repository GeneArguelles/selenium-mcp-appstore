#!/usr/bin/env bash
# ======================================================
# install_system_chrome.sh — Render-safe Playwright Chromium installer
# ------------------------------------------------------
# Uses Microsoft Playwright's CDN (fast, stable) instead of Google snapshots
# ======================================================

set -e
set -o pipefail

echo "[INFO] Installing Playwright Chromium (user-space)..."

CHROME_DIR="/opt/render/project/src/.local/chrome"
CHROME_BIN="$CHROME_DIR/chrome-linux/chrome"
PLAYWRIGHT_VERSION="1.47.2"

mkdir -p "$CHROME_DIR"
cd "$CHROME_DIR"

# ------------------------------------------------------
# Step 1: Download Playwright’s Chromium bundle
# ------------------------------------------------------
PLAYWRIGHT_ZIP_URL="https://playwright.azureedge.net/builds/chromium/1090/chromium-linux.zip"
PLAYWRIGHT_ZIP="$CHROME_DIR/chromium-linux.zip"

if [ -f "$CHROME_BIN" ]; then
  echo "[INFO] ✅ Existing Chromium binary found at $CHROME_BIN"
else
  echo "[INFO] Downloading Chromium build from Playwright CDN..."
  curl -L -f -o "$PLAYWRIGHT_ZIP" "$PLAYWRIGHT_ZIP_URL" --progress-bar || {
    echo "[ERROR] ❌ Failed to download Playwright Chromium bundle."
    exit 1
  }

  echo "[INFO] Extracting Chromium..."
  unzip -q "$PLAYWRIGHT_ZIP" -d "$CHROME_DIR" || {
    echo "[ERROR] ❌ Failed to unzip Playwright Chromium archive."
    exit 1
  }
  rm -f "$PLAYWRIGHT_ZIP"
fi

# ------------------------------------------------------
# Step 2: Verify binary presence
# ------------------------------------------------------
if [ -x "$CHROME_BIN" ]; then
  echo "[INFO] ✅ Chromium (Playwright) installed successfully at $CHROME_BIN"
  "$CHROME_BIN" --version || echo "[WARN] Chrome version check failed (non-fatal)."
else
  echo "[ERROR] ❌ Chromium binary not found after extraction!"
  exit 1
fi

# ------------------------------------------------------
# Step 3: Export env var for runtime
# ------------------------------------------------------
echo "export CHROME_BINARY=$CHROME_BIN" >> ~/.bashrc
echo "[INFO] Environment variable CHROME_BINARY set to $CHROME_BIN"

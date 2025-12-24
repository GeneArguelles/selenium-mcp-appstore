#!/usr/bin/env bash
# ==========================================================
# install_chromedriver.sh — Auto-fetch correct ChromeDriver (Cross-platform)
# ==========================================================

set -e
echo "[INFO] Starting ChromeDriver auto-installer..."

# ----------------------------------------------------------
# 1️⃣ Detect OS Platform
# ----------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"
TARGET_DIR="chromedriver"

if [[ "$OS" == "Darwin" ]]; then
  PLATFORM="mac-arm64"
  echo "[INFO] Detected macOS ARM64 (Apple Silicon)"
elif [[ "$OS" == "Linux" ]]; then
  PLATFORM="linux64"
  echo "[INFO] Detected Linux x86_64"
else
  echo "[ERROR] Unsupported platform: $OS"
  exit 1
fi

# ----------------------------------------------------------
# 2️⃣ Detect Chrome Version
# ----------------------------------------------------------
CHROME_PATH="${CHROME_PATH:-/opt/render/project/src/.local/chrome/chrome-linux/chrome}"
CHROME_VERSION_ENV="${CHROME_VERSION:-}"

if [ -n "$CHROME_VERSION_ENV" ]; then
  CHROME_VERSION="$CHROME_VERSION_ENV"
  echo "[INFO] Using CHROME_VERSION from env: $CHROME_VERSION"
elif [ -x "$CHROME_PATH" ]; then
  CHROME_VERSION=$("$CHROME_PATH" --version | grep -oE '[0-9]+(\.[0-9]+)+' | head -n 1)
  echo "[INFO] Detected Chrome version: $CHROME_VERSION"
elif command -v google-chrome >/dev/null 2>&1; then
  CHROME_VERSION=$(google-chrome --version | grep -oE '[0-9]+(\.[0-9]+)+' | head -n 1)
  echo "[INFO] Detected system Chrome version: $CHROME_VERSION"
else
  echo "[WARN] Could not detect Chrome binary, defaulting to version 120.0.6099.18"
  CHROME_VERSION="120.0.6099.18"
fi

# ----------------------------------------------------------
# 3️⃣ Download + Extract
# ----------------------------------------------------------
BASE_URL="https://storage.googleapis.com/chrome-for-testing-public"
CHROMEDRIVER_URL="$BASE_URL/${CHROME_VERSION}/${PLATFORM}/chromedriver-${PLATFORM}.zip"

echo "[INFO] Download URL: $CHROMEDRIVER_URL"
mkdir -p "$TARGET_DIR"

echo "[INFO] Downloading ChromeDriver..."
curl -L -o "$TARGET_DIR/chromedriver.zip" "$CHROMEDRIVER_URL" || {
  echo "[ERROR] Failed to download ChromeDriver."
  exit 1
}

echo "[INFO] Extracting ChromeDriver..."
unzip -o "$TARGET_DIR/chromedriver.zip" -d "$TARGET_DIR" >/dev/null 2>&1 || {
  echo "[ERROR] Failed to unzip ChromeDriver archive."
  exit 1
}

# Normalize structure
if [ -f "$TARGET_DIR/chromedriver-${PLATFORM}/chromedriver" ]; then
  mv -f "$TARGET_DIR/chromedriver-${PLATFORM}/chromedriver" "$TARGET_DIR/chromedriver"
  rm -rf "$TARGET_DIR/chromedriver-${PLATFORM}"
  echo "[INFO] Moved ChromeDriver binary to: $TARGET_DIR/chromedriver"
fi

chmod +x "$TARGET_DIR/chromedriver" || true

# ----------------------------------------------------------
# 4️⃣ Print summary
# ----------------------------------------------------------
echo "=========================================================="
if [ -f "$TARGET_DIR/chromedriver" ]; then
  echo "[INFO] ✅ ChromeDriver installation complete!"
  if [[ "$OS" == "Linux" ]]; then
    "$TARGET_DIR/chromedriver" --version || echo "[WARN] Unable to run version check"
  else
    echo "[INFO] Skipping version check (non-Linux host)."
  fi
else
  echo "[ERROR] ❌ ChromeDriver not found in $TARGET_DIR/"
  ls -R "$TARGET_DIR"
fi
echo "=========================================================="

exit 0

#!/bin/bash
# ==========================================================
# mac_install_chromefortesting.sh — v3
# Secure Chrome-for-Testing installer for macOS
# Dynamically detects installed Chrome version and downloads
# the exact matching Chrome-for-Testing + ChromeDriver build.
# ==========================================================

set -e

INSTALL_DIR="$HOME/chrome-for-testing"
ENV_FILE="$(dirname "$0")/.env"

echo "=========================================================="
echo "[INFO] mac_install_chromefortesting.sh (v3)"
echo "=========================================================="

# ----------------------------------------------------------
# 1️⃣ Detect current Chrome version on macOS
# ----------------------------------------------------------
if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  echo "[INFO] Detecting installed Chrome version..."
  INSTALLED_VERSION=$("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version | awk '{print $3}')
  echo "[INFO] Installed Chrome version: ${INSTALLED_VERSION}"
else
  echo "[WARN] Google Chrome not found — using fallback version (latest stable)."
  INSTALLED_VERSION=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json | jq -r '.channels.Stable.version')
  echo "[INFO] Fallback Chrome version: ${INSTALLED_VERSION}"
fi

CHROME_VERSION="${INSTALLED_VERSION}"
CHROME_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/mac-x64/chrome-mac-x64.zip"
DRIVER_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/mac-x64/chromedriver-mac-x64.zip"

echo "[INFO] Using Chrome version: ${CHROME_VERSION}"
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

# ----------------------------------------------------------
# 2️⃣ Download Chrome + ChromeDriver archives
# ----------------------------------------------------------
echo "[INFO] Downloading Chrome bundle..."
curl -LO "${CHROME_URL}" --silent --show-error --fail || {
  echo "[ERROR] ❌ Failed to download Chrome bundle from ${CHROME_URL}"
  exit 1
}

echo "[INFO] Downloading ChromeDriver bundle..."
curl -LO "${DRIVER_URL}" --silent --show-error --fail || {
  echo "[ERROR] ❌ Failed to download ChromeDriver bundle from ${DRIVER_URL}"
  exit 1
}

# ----------------------------------------------------------
# 3️⃣ Extract archives and locate Chromium app
# ----------------------------------------------------------
echo "[INFO] Extracting archives..."
unzip -o "chrome-mac-x64.zip" >/dev/null
unzip -o "chromedriver-mac-x64.zip" >/dev/null

CHROME_APP_DIR=$(find "${INSTALL_DIR}" -type d -name "Chromium.app" | head -n 1)
if [ -z "$CHROME_APP_DIR" ]; then
  echo "[ERROR] ❌ Chromium.app not found after extraction."
  exit 1
fi

CHROME_APP_BIN="${CHROME_APP_DIR}/Contents/MacOS/Chromium"
CHROMEDRIVER_SRC=$(find "${INSTALL_DIR}" -type f -name "chromedriver" | head -n 1)
CHROMEDRIVER_DEST="$(dirname "${CHROME_APP_BIN}")/chromedriver"

# ----------------------------------------------------------
# 4️⃣ Move ChromeDriver into Chrome bundle
# ----------------------------------------------------------
echo "[INFO] Moving ChromeDriver into Chromium.app..."
mv -f "$CHROMEDRIVER_SRC" "$CHROMEDRIVER_DEST" || {
  echo "[ERROR] ❌ Failed to move ChromeDriver."
  exit 1
}

# ----------------------------------------------------------
# 5️⃣ Update .env with dynamic paths
# ----------------------------------------------------------
echo "[INFO] Updating .env with detected Chrome paths..."
{
  echo ""
  echo "# === Added by mac_install_chromefortesting.sh (v3) ==="
  echo "LOCAL_MODE=true"
  echo "LOCAL_CHROME_PATH=${CHROME_APP_BIN}"
  echo "LOCAL_CHROMEDRIVER_PATH=${CHROMEDRIVER_DEST}"
  echo "CHROME_VERSION=${CHROME_VERSION}"
} >> "${ENV_FILE}"

# ----------------------------------------------------------
# 6️⃣ Clean up temp files
# ----------------------------------------------------------
rm -rf "${INSTALL_DIR}/chromedriver-mac-x64"
rm -f "${INSTALL_DIR}/chrome-mac-x64.zip" "${INSTALL_DIR}/chromedriver-mac-x64.zip"

# ----------------------------------------------------------
# 7️⃣ Verify binaries
# ----------------------------------------------------------
echo "[INFO] Verifying ChromeDriver..."
"$CHROMEDRIVER_DEST" --version || echo "[WARN] Could not verify chromedriver execution."

echo "=========================================================="
echo "[✅] Chrome for Testing (v${CHROME_VERSION}) installed successfully!"
echo "[INFO] Chromium path: ${CHROME_APP_BIN}"
echo "[INFO] ChromeDriver path: ${CHROMEDRIVER_DEST}"
echo "[INFO] .env updated: ${ENV_FILE}"
echo "=========================================================="

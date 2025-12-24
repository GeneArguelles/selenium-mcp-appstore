#!/usr/bin/env bash
set -euo pipefail
VER="120.0.6099.18"
URL="https://storage.googleapis.com/chrome-for-testing-public/${VER}/linux64/chromedriver-linux64.zip"

echo "[INFO] Bundling ChromeDriver ${VER}"
rm -rf chromedriver-linux64 chromedriver/chromedriver chromedriver-linux64.zip || true
curl -L -o chromedriver-linux64.zip "$URL"
unzip -o -q chromedriver-linux64.zip
mkdir -p chromedriver
mv -f chromedriver-linux64/chromedriver chromedriver/chromedriver
chmod +x chromedriver/chromedriver
rm -rf chromedriver-linux64 chromedriver-linux64.zip
./chromedriver/chromedriver --version
echo "[OK] ChromeDriver is ready at chromedriver/chromedriver"

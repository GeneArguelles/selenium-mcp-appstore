#!/usr/bin/env bash
# ==========================================================
# install_chrome_runtime.sh — runtime installation script
# Runs inside the live Render runtime (writable FS)
# ==========================================================

set -e
echo "[INFO] Installing Google Chrome + ChromeDriver at runtime..."

apt-get update -y
apt-get install -y wget gnupg unzip curl

# Add Google Chrome repo
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
  > /etc/apt/sources.list.d/google-chrome.list

apt-get update -y
apt-get install -y google-chrome-stable chromium-chromedriver

echo "[INFO] Chrome installed successfully."
google-chrome --version
chromedriver --version

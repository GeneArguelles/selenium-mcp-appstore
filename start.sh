#!/usr/bin/env bash
# ==========================================================
# start.sh — Start Selenium MCP (local or Render)
# ==========================================================
set -e

echo "=========================================================="
echo "[INFO] Starting Selenium MCP startup sequence..."
echo "=========================================================="
echo "[INFO] MCP_VERSION auto-handled internally by server.py"

# === Setup environment ===
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs/deploy_$TIMESTAMP"
mkdir -p "$LOG_DIR"
echo "[INFO] Logs rotated. Active folder: $LOG_DIR"

# === Load .env safely ===
if [ -f .env ]; then
  echo "[INFO] Loading environment variables from .env safely..."
  set -a
  source .env
  set +a
else
  echo "[WARN] No .env file found."
fi

# === Verify ChromeDriver and Chrome binaries ===
if [ ! -f ./chromedriver/chromedriver ]; then
  echo "[ERROR] Missing ChromeDriver at ./chromedriver/chromedriver"
  exit 1
fi
echo "[INFO] ✅ ChromeDriver binary present at ./chromedriver/chromedriver"

if [ -z "$CHROME_BINARY" ]; then
  echo "[WARN] CHROME_BINARY not set. Attempting to auto-detect..."
  export CHROME_BINARY="$(which google-chrome || which chromium || true)"
fi

if [ ! -x "$CHROME_BINARY" ]; then
  echo "[ERROR] CHROME_BINARY is not executable or not found: $CHROME_BINARY"
  exit 1
fi
echo "[INFO] ✅ Chrome binary confirmed: $CHROME_BINARY"

# === Launch MCP Server ===
PORT="${PORT:-10000}"
UVICORN_CMD="uvicorn mcp_server:app --host 0.0.0.0 --port $PORT"
echo "[INFO] Launching MCP Server via Uvicorn on port 10000..."
# NOTE: 'mcp_server:app' must match the filename and FastAPI app variable in mcp_server.py

if [[ "$RENDER" == "true" || "$PWD" == *"/opt/render"* ]]; then
  echo "[INFO] Detected Render environment. Starting in foreground..."
  $UVICORN_CMD
else
  echo "[INFO] Starting in background (local dev)..."
  nohup bash -c "$UVICORN_CMD" > "$LOG_DIR/server.log" 2>&1 &
fi

# === Health check loop ===
echo "[INFO] Waiting for MCP local health check..."
for i in {1..15}; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:10000/mcp/schema)
  if [[ "$STATUS" == "200" ]]; then
    echo "[✅ READY] MCP schema available locally after ${i}s"
    break
  fi
  echo "[WAIT] Attempt $i/15: not ready (HTTP $STATUS). Retrying..."
  sleep 1
done

# === Optional warmup ping to public endpoint ===
if [ -n "$RENDER_EXTERNAL_URL" ]; then
  SANITIZED_URL="${RENDER_EXTERNAL_URL#https://}"
  echo "=========================================================="
  echo "[WARMUP] Warming MCP endpoint: https://$SANITIZED_URL/mcp/schema"
  echo "=========================================================="
  for i in {1..10}; do
    TIME=$(curl -s -o /dev/null -w "%{time_total}" "https://$SANITIZED_URL/mcp/schema")
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$SANITIZED_URL/mcp/schema")
    if [[ "$STATUS" == "200" ]]; then
      echo "[WARMUP ✅] Success at attempt $i → $TIME sec"
      break
    else
      echo "❌ [WARMUP] Not ready (HTTP $STATUS). Retrying in 3s..."
      sleep 3
    fi
  done
fi

echo "----------------------------------------------------------"
echo "[WARMUP] MCP warmup complete."
echo "=========================================================="
echo "[INFO] MCP deployment complete and fully warmed."
echo "[INFO] Logs: $LOG_DIR/mcp.log"
echo "=========================================================="
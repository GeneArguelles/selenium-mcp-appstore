#!/bin/bash
# ─────────────────────────────────────────────
# MCP Restart Protocol — Gene Arguelles, 2025
# Includes: process cleanup, health-check, logging, and client auto-launch
# ─────────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$PROJECT_DIR/startup_log.txt"

echo "🔧 Killing stale processes on ports 8000 and 8001..."
lsof -ti :8000 :8001 | xargs kill -9 2>/dev/null

echo "🧹 Cleaning up old ChromeDriver instances..."
pkill -f chromedriver 2>/dev/null

echo "🛡️  Removing potential ChromeDriver quarantine flag..."
if [ -f "/usr/local/bin/chromedriver" ]; then
  sudo xattr -d com.apple.quarantine /usr/local/bin/chromedriver 2>/dev/null
  sudo chmod +x /usr/local/bin/chromedriver 2>/dev/null
fi

echo "⚙️  Activating Python virtual environment..."
source "$PROJECT_DIR/.venv/bin/activate"

echo "🚀 Starting Uvicorn MCP server..."
uvicorn mcp_server:app --reload --port 8001 > >(tee -a "$LOG_FILE") 2>&1 &

# Give the server a few seconds to spin up
sleep 3

# Log timestamp
echo "──────────────────────────────────────────────" >> "$LOG_FILE"
echo "🕒 $(date '+%Y-%m-%d %H:%M:%S') — MCP Restart" >> "$LOG_FILE"

echo "🩺 Checking MCP server health..."
if curl -s http://localhost:8001/health | grep -q '"status":"ok"'; then
  echo "✅ MCP server is healthy and responding." | tee -a "$LOG_FILE"
else
  echo "❌ MCP health check failed. Check Uvicorn logs." | tee -a "$LOG_FILE"
  exit 1
fi

echo "💬 Launching MCP client..."
python "$PROJECT_DIR/mcp_client.py" --url http://localhost:8001/mcp/invoke | tee -a "$LOG_FILE"

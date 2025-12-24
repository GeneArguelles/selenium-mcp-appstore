#!/bin/bash

# git-deploy.sh — Auto-validate, run, and push your FastAPI MCP server
# Make sure you're in the correct git repo directory before running

set -e  # Exit on any error
SERVER_FILE="server.py"
PORT=10000

# Step 1: Validate Python syntax
echo "[🔍] Validating $SERVER_FILE..."
python3 -m py_compile $SERVER_FILE
echo "[✅] Syntax check passed."

# Step 2: Kill any process using PORT (optional safety)
echo "[🛑] Checking for existing processes on port $PORT..."
PID=$(lsof -ti tcp:$PORT)
if [ -n "$PID" ]; then
  echo "[⚠️ ] Killing process on port $PORT (PID=$PID)..."
  kill -9 $PID
fi

# Step 3: Start server in background
echo "[🚀] Starting MCP server locally on port $PORT..."
nohup uvicorn server:app --host 0.0.0.0 --port $PORT > uvicorn.log 2>&1 &
sleep 2
echo "[📡] Server started. Log: uvicorn.log"

# Step 4: Git add, commit, and push
echo "[📁] Staging changes..."
git add $SERVER_FILE

# Generate version commit message from MCP_VERSION
VERSION=$(grep "MCP_VERSION" $SERVER_FILE | tail -1 | sed 's/.*"\(v[0-9a-z]*\)".*/\1/')
if [ -z "$VERSION" ]; then
  VERSION="autocommit"
fi

echo "[📦] Committing as: Update $SERVER_FILE ($VERSION)"
git commit -m "Update $SERVER_FILE ($VERSION)"

echo "[🚀] Pushing to remote..."
git push

echo "[✅] Done. Server running on http://localhost:$PORT"

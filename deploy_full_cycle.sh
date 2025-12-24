#!/bin/bash
# ==========================================================
# deploy_full_cycle.sh
# Unified Render deploy & warm-up pipeline for Selenium MCP
# Author: Gene Arguelles + GPT-5 Assistant
# ==========================================================

set -e  # Exit immediately on error

# ------------------------------------------
# 0. CONFIGURATION
# ------------------------------------------
APP_URL="https://selenium-mcp.onrender.com"
SCHEMA_PATH="/mcp/schema"
RENDER_REMOTE="render"
WARMUP_ATTEMPTS=3

# ------------------------------------------
# 1. VERIFY NETWORK CONNECTIVITY
# ------------------------------------------
echo "=========================================================="
echo "[STEP 1] Verifying network connectivity..."
echo "=========================================================="

if ping -c 2 render.com &> /dev/null; then
    echo "[INFO] ✅ Wi-Fi and Render network reachable."
else
    echo "[ERROR] ❌ Network down. Please reconnect before deploying."
    exit 1
fi

# ------------------------------------------
# 2. AUTO-INCREMENT VERSION
# ------------------------------------------
echo "=========================================================="
echo "[STEP 2] Auto-incrementing MCP version..."
echo "=========================================================="

VERSION_TAG="v$(date +%Y%m%d%H%M%S)"
export MCP_VERSION="$VERSION_TAG"
echo "[INFO] MCP_VERSION set to $MCP_VERSION"

# Update local environment variable file (optional)
if [ -f .env ]; then
    sed -i '' "s/^MCP_VERSION=.*/MCP_VERSION=$MCP_VERSION/" .env || echo "MCP_VERSION=$MCP_VERSION" >> .env
fi

# ------------------------------------------
# 3. COMMIT AND PUSH TO RENDER
# ------------------------------------------
echo "=========================================================="
echo "[STEP 3] Pushing new build to Render..."
echo "=========================================================="

git add .
git commit -m "Deploy MCP ${MCP_VERSION}" || echo "[INFO] No new changes to commit."
git push $RENDER_REMOTE main

# ------------------------------------------
# 4. DEPLOY WAIT & WARM-UP TESTS
# ------------------------------------------
echo "=========================================================="
echo "[STEP 4] Warming up Render deployment..."
echo "=========================================================="

sleep 30  # Give Render time to start container
total_latency=0

for i in $(seq 1 $WARMUP_ATTEMPTS); do
  echo "[INFO] 🔁 Warm-up attempt #$i (GET)"
  start_time=$(date +%s%3N)
  status_get=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$APP_URL$SCHEMA_PATH")
  end_time=$(date +%s%3N)
  latency=$((end_time - start_time))
  echo "[INFO] GET returned $status_get in ${latency}ms"
  total_latency=$((total_latency + latency))

  echo "[INFO] 🔁 Warm-up attempt #$i (POST)"
  start_time=$(date +%s%3N)
  status_post=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" "$APP_URL$SCHEMA_PATH")
  end_time=$(date +%s%3N)
  latency=$((end_time - start_time))
  echo "[INFO] POST returned $status_post in ${latency}ms"
  total_latency=$((total_latency + latency))

  sleep 3
done

avg_latency=$((total_latency / (WARMUP_ATTEMPTS * 2)))
echo "=========================================================="
echo "[INFO] 🌡️  Average schema latency across all attempts: ${avg_latency}ms"
echo "=========================================================="

# ------------------------------------------
# 5. VALIDATION TEST
# ------------------------------------------
echo "=========================================================="
echo "[STEP 5] Verifying schema structure..."
echo "=========================================================="

curl -s "$APP_URL$SCHEMA_PATH" | jq '.tools[0].name' || echo "[WARN] jq failed to parse tools array — check JSON integrity."

# ------------------------------------------
# 6. SUCCESS BANNER
# ------------------------------------------
echo "=========================================================="
echo "[SUCCESS] ✅ MCP ${MCP_VERSION} deployed and warmed up!"
echo "[READY] Copy this URL into Agent Builder:"
echo "         ${APP_URL}${SCHEMA_PATH}"
echo "=========================================================="

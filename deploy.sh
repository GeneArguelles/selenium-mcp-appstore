#!/usr/bin/env bash
# ==========================================================
# DEPLOY ROUTINE FOR SELENIUM MCP SERVER
# ==========================================================
# This script:
#  1. Commits and pushes to Render git repo
#  2. Waits for deployment to go live
#  3. Generates a new MCP connection URL with nonce
#  4. Validates that the /live endpoint is MCP-compliant
#  5. Prints the URL for copy-paste into Agent Builder
# ==========================================================

BASE_URL="https://selenium-mcp.onrender.com"
VERSION="v20251020"

# --- Generate Nonce ---
NONCE=$(date +%s%N | shasum | cut -c1-10)
MCP_URL="${BASE_URL}/${VERSION}/live?nonce=${NONCE}&refresh=true"

# --- Commit & Push ---
echo "==========================================================="
echo "[DEPLOY] 🛠  Committing and pushing latest changes..."
echo "==========================================================="
git add .
git commit -m "Auto-deploy MCP server $(date)"
git push
echo "[DEPLOY] ✅ Push completed — waiting for Render to redeploy..."

# --- Wait Loop for Render (adjust if Render builds take longer) ---
echo "[DEPLOY] ⏳ Waiting 40 seconds for redeploy to finish..."
sleep 40

# --- Validate Endpoint ---
echo "[DEPLOY] 🔍 Validating endpoint: $MCP_URL"
HTTP_STATUS=$(curl -s -o response.json -w "%{http_code}" "$MCP_URL")

if [ "$HTTP_STATUS" -ne 200 ]; then
  echo "[DEPLOY] ❌ Endpoint returned HTTP $HTTP_STATUS"
  cat response.json
  exit 1
fi

TOOLS_COUNT=$(jq '.tools | length' response.json)
TYPE=$(jq -r '.type' response.json)

echo "-----------------------------------------------------------"
echo "[DEPLOY] MCP URL: $MCP_URL"
echo "[DEPLOY] HTTP Status: $HTTP_STATUS"
if [ "$TOOLS_COUNT" -gt 0 ]; then
  echo "[DEPLOY] ✅ Found $TOOLS_COUNT tool(s) in manifest."
else
  echo "[DEPLOY] ⚠️ No tools found!"
fi
if [ "$TYPE" == "mcp_server" ]; then
  echo "[DEPLOY] ✅ Type is MCP-compliant."
else
  echo "[DEPLOY] ⚠️ Type key missing or incorrect ($TYPE)."
fi
echo "-----------------------------------------------------------"
echo "[DEPLOY] ✅ Done. Copy the above MCP URL into Agent Builder."
echo "==========================================================="

# Optional: remove temporary file
rm -f response.json

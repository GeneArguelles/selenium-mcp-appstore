#!/usr/bin/env bash
# ==========================================================
# force_refresh_mcp.sh (v2025.10.20b)
# Purpose:
#   Generate a unique cache-busting MCP URL for Agent Builder,
#   copy it to the clipboard, and verify manifest accessibility.
# ==========================================================

BASE_URL="https://selenium-mcp.onrender.com/v20251020/live"

# Generate random nonce (8-character alphanumeric)
NONCE=$(openssl rand -hex 4)

# Build full cache-busting URL
FINAL_URL="${BASE_URL}?nonce=${NONCE}"

echo "=========================================================="
echo "🔁  MCP Cache-Bypass URL Generator"
echo "=========================================================="
echo "[INFO] Generated Nonce: ${NONCE}"
echo "[INFO] Full URL:"
echo "   ${FINAL_URL}"
echo ""

# Copy to clipboard (macOS pbcopy or Linux xclip/xsel)
if command -v pbcopy >/dev/null 2>&1; then
  echo -n "${FINAL_URL}" | pbcopy
  echo "[INFO] ✅ URL copied to clipboard (macOS pbcopy)."
elif command -v xclip >/dev/null 2>&1; then
  echo -n "${FINAL_URL}" | xclip -selection clipboard
  echo "[INFO] ✅ URL copied to clipboard (Linux xclip)."
elif command -v xsel >/dev/null 2>&1; then
  echo -n "${FINAL_URL}" | xsel --clipboard
  echo "[INFO] ✅ URL copied to clipboard (Linux xsel)."
else
  echo "[WARN] Clipboard utility not found. Copy manually:"
  echo "       ${FINAL_URL}"
fi

# Optional: quick validation ping
echo ""
echo "[INFO] Checking endpoint status..."
HTTP_CODE=$(curl -s -o /tmp/mcp_manifest.json -w "%{http_code}" -X POST "${FINAL_URL}")

if [ "$HTTP_CODE" == "200" ]; then
  TYPE=$(jq -r '.type' /tmp/mcp_manifest.json 2>/dev/null)
  NAME=$(jq -r '.server_info.name' /tmp/mcp_manifest.json 2>/dev/null)
  TOOL=$(jq -r '.tools[].name' /tmp/mcp_manifest.json 2>/dev/null)
  echo "[PASS] Endpoint reachable (HTTP ${HTTP_CODE})"
  echo "       Type: ${TYPE}"
  echo "       Name: ${NAME}"
  echo "       Tool: ${TOOL}"
else
  echo "[FAIL] Endpoint returned HTTP ${HTTP_CODE}"
fi

echo ""
echo "[INFO] Paste the URL above into Agent Builder's MCP field."
echo "=========================================================="

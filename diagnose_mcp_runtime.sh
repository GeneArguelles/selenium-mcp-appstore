#!/bin/bash
# ==========================================================
# diagnose_mcp_runtime.sh
# Selenium MCP Post-Deployment Diagnostic Suite
# Version: 2025.10.19d
# ==========================================================

# URL root (update if your MCP host changes)
BASE_URL="https://selenium-mcp.onrender.com"

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
RESET="\033[0m"

# Divider
divider() { echo -e "${BLUE}----------------------------------------------------------${RESET}"; }

# Check helper
check_endpoint() {
  local name="$1"
  local url="$2"
  local expect="$3"

  echo -e "\n${YELLOW}${name}${RESET}"
  divider
  response=$(curl -s -w "\n%{http_code}" -H "Cache-Control: no-cache" "$url")
  http_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')

  # Save output to temp for optional inspection
  echo "$body" > "/tmp/mcp_${name// /_}.json"

  if [[ "$http_code" == "200" ]]; then
    # Optional content checks
    if echo "$body" | jq -e "$expect" &>/dev/null; then
      echo -e "${GREEN}✅ PASS${RESET} — ${url} [HTTP ${http_code}]"
    else
      echo -e "${RED}⚠️  WARN${RESET} — ${url} [HTTP ${http_code}] Content mismatch"
    fi
  else
    echo -e "${RED}❌ FAIL${RESET} — ${url} [HTTP ${http_code}]"
  fi
}

# ==========================================================
# Begin diagnostics
# ==========================================================
echo -e "\n=========================================================="
echo -e " 🧩 MCP Runtime Diagnostics — Selenium MCP"
echo -e "=========================================================="
echo -e "Target: ${BASE_URL}"
divider

# 1️⃣ /health
check_endpoint "1️⃣ /health — server health" \
  "${BASE_URL}/health" \
  '.status'

# 2️⃣ Root Manifest /
check_endpoint "2️⃣ Root Manifest — MCP discovery" \
  "${BASE_URL}/" \
  '.type == "mcp" or .type == "mcp_server"'

# 3️⃣ /mcp/schema
check_endpoint "3️⃣ /mcp/schema — canonical schema" \
  "${BASE_URL}/mcp/schema" \
  '.tools | length > 0'

# 4️⃣ /live
nonce=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)
check_endpoint "4️⃣ /live — cache-bypass alias" \
  "${BASE_URL}/live?nonce=${nonce}" \
  '.message or .tools'

# 5️⃣ /mcp/invoke
echo -e "\n${YELLOW}5️⃣ /mcp/invoke — sample Selenium command${RESET}"
divider
invoke_payload='{"tool":"selenium_open_page","arguments":{"url":"https://example.com"}}'
response=$(curl -s -w "\n%{http_code}" -X POST -H "Content-Type: application/json" \
  -d "$invoke_payload" "${BASE_URL}/mcp/invoke")

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [[ "$http_code" == "200" ]]; then
  title=$(echo "$body" | jq -r '.title // empty')
  if [[ -n "$title" ]]; then
    echo -e "${GREEN}✅ PASS${RESET} — Selenium invoked successfully (${title}) [HTTP ${http_code}]"
  else
    echo -e "${RED}⚠️  WARN${RESET} — /mcp/invoke returned no title [HTTP ${http_code}]"
  fi
else
  echo -e "${RED}❌ FAIL${RESET} — /mcp/invoke [HTTP ${http_code}]"
fi

divider
echo -e "\n${BLUE}Diagnostics complete. JSON snapshots saved to /tmp/mcp_*.json${RESET}\n"

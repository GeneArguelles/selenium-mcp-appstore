#!/usr/bin/env bash
# ==========================================================
# 🧩 Local MCP Validation Suite — Selenium MCP
# Purpose: Quickly verify manifest, schema, and invoke routes
# ==========================================================

BASE_URL="http://127.0.0.1:10000"
GREEN="\033[1;32m"
RED="\033[1;31m"
NC="\033[0m"

echo -e "\n=========================================================="
echo -e " 🧠 Local MCP Validation Suite — Selenium MCP"
echo -e "==========================================================\n"

# 1️⃣ Root manifest
echo -e "1️⃣ Checking root manifest (${BASE_URL}/)..."
HTTP_CODE=$(curl -s -o /tmp/mcp_root.json -w "%{http_code}" "$BASE_URL/")
if [[ "$HTTP_CODE" == "200" ]]; then
  echo -e "${GREEN}✅ PASS${NC} — Root manifest reachable [HTTP 200]"
  jq . /tmp/mcp_root.json | head -20
else
  echo -e "${RED}❌ FAIL${NC} — Root manifest check failed [HTTP $HTTP_CODE]"
  exit 1
fi

# 2️⃣ Schema endpoint
echo -e "\n2️⃣ Checking schema endpoint (${BASE_URL}/mcp/schema)..."
HTTP_CODE=$(curl -s -o /tmp/mcp_schema.json -w "%{http_code}" "$BASE_URL/mcp/schema")
if [[ "$HTTP_CODE" == "200" ]]; then
  echo -e "${GREEN}✅ PASS${NC} — Schema endpoint reachable [HTTP 200]"
  jq . /tmp/mcp_schema.json | head -20
else
  echo -e "${RED}❌ FAIL${NC} — Schema endpoint check failed [HTTP $HTTP_CODE]"
  exit 1
fi

# 3️⃣ Invoke endpoint
echo -e "\n3️⃣ Running sample invoke (${BASE_URL}/mcp/invoke)..."
HTTP_CODE=$(curl -s -o /tmp/mcp_invoke.json -w "%{http_code}" \
  -X POST "$BASE_URL/mcp/invoke" \
  -H "Content-Type: application/json" \
  -d '{"tool":"selenium_open_page","arguments":{"url":"https://example.com"}}')

if [[ "$HTTP_CODE" == "200" ]]; then
  echo -e "${GREEN}✅ PASS${NC} — Invoke endpoint reachable [HTTP 200]"
  jq . /tmp/mcp_invoke.json
else
  echo -e "${RED}❌ FAIL${NC} — Invoke test failed [HTTP $HTTP_CODE]"
  exit 1
fi

echo -e "\n=========================================================="
echo -e "${GREEN}🎉 All MCP local validation checks PASSED!${NC}"
echo -e "==========================================================\n"

#!/usr/bin/env bash
BASE_URL="https://selenium-mcp.onrender.com"

echo "=========================================================="
echo "✅ Post-Deploy Verification — MCP Runtime"
echo "=========================================================="

for ENDPOINT in "/" "/health" "/mcp/schema" "/live" "/mcp/invoke"; do
  # Default method = GET, except invoke = POST
  if [ "$ENDPOINT" = "/mcp/invoke" ]; then
    METHOD="-X POST -H 'Content-Type: application/json' \
            -d '{\"tool\":\"selenium_open_page\",\"arguments\":{\"url\":\"https://example.com\"}}'"
  else
    METHOD="-X GET"
  fi

  STATUS=$(bash -c "curl -s -o /dev/null -w '%{http_code}' $METHOD \"$BASE_URL$ENDPOINT\"")
  if [ "$STATUS" == "200" ]; then
    echo -e "[\033[0;32mPASS\033[0m] $ENDPOINT — $STATUS"
  else
    echo -e "[\033[0;31mFAIL\033[0m] $ENDPOINT — $STATUS"
  fi
done

#!/usr/bin/env bash
set -euo pipefail
command -v jq >/dev/null || { echo "jq is required"; exit 1; }

BASE="${BASE:-https://selenium-mcp-appstore.onrender.com/mcp/}"

# 1) Initialize parameters
SID=$(
  curl --http1.1 -sS -D - -o /dev/null \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","clientInfo":{"name":"smoke","version":"0.1"},"capabilities":{}}}' \
    "$BASE" \
  | awk 'BEGIN{IGNORECASE=1} $1=="mcp-session-id:"{print $2}' \
  | tr -d '\r'
)

# 2) Initialize notifications
curl --http1.1 -sS -i \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "Mcp-Session-Id: $SID" \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  "$BASE" >/dev/null

# 3) TOOLS block
TOOLS_JSON=$(
  curl --http1.1 -sS -N \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -H "Mcp-Session-Id: $SID" \
    -H 'MCP-Protocol-Version: 2025-06-18' \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
    "$BASE" \
  | sed -n 's/^data: //p' \
  | head -n 1
)

echo "$TOOLS_JSON" | jq -e '.result.tools | length > 0' >/dev/null
echo "OK MCP smoke passed (SID=$SID)"

# 4) create browser session (BID)
BID=$(
  curl --http1.1 -sS -N \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -H "Mcp-Session-Id: $SID" \
    -H 'MCP-Protocol-Version: 2025-06-18' \
    -d '{"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"create_session","arguments":{}}}' \
    "$BASE" \
  | sed -n 's/^data: //p' \
  | jq -r '.result.content[0].text' \
  | jq -r '.session_id'
)

echo "BID=$BID"

# 5) open_page
curl --http1.1 -sS -N \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "Mcp-Session-Id: $SID" \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -d "$(jq -nc --arg bid "$BID" \
        '{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"open_page","arguments":{"session_id":$bid,"url":"https://example.com"}}}')" \
  "$BASE" \
| sed -n 's/^data: //p'

# 6) get_text h1
H1=$(
  curl --http1.1 -sS -N \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -H "Mcp-Session-Id: $SID" \
    -H 'MCP-Protocol-Version: 2025-06-18' \
    -d "$(jq -nc --arg bid "$BID" \
          '{"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"get_text","arguments":{"session_id":$bid,"css_selector":"h1"}}}')" \
    "$BASE" \
  | sed -n 's/^data: //p' \
  | jq -r '.result.content[0].text' \
  | jq -r '.text'
)

echo "H1=$H1"
test "$H1" = "Example Domain" || { echo "FAIL: unexpected h1=$H1"; exit 1; }

# 7) screenshot -> write PNG
curl --http1.1 -sS -N \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "Mcp-Session-Id: $SID" \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -d "$(jq -nc --arg bid "$BID" \
        '{"jsonrpc":"2.0","id":13,"method":"tools/call","params":{"name":"screenshot","arguments":{"session_id":$bid}}}')" \
  "$BASE" \
| sed -n 's/^data: //p' \
| jq -r '.result.content[0].text' \
| jq -r '.image_base64' \
| base64 --decode > smoke.png

echo "Wrote smoke.png ($(wc -c < smoke.png) bytes)"

# 8) close browser session
curl --http1.1 -sS -N \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "Mcp-Session-Id: $SID" \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -d "$(jq -nc --arg bid "$BID" \
        '{"jsonrpc":"2.0","id":14,"method":"tools/call","params":{"name":"close_session","arguments":{"session_id":$bid}}}')" \
  "$BASE" \
| sed -n 's/^data: //p'

echo "OK browser smoke test passed"
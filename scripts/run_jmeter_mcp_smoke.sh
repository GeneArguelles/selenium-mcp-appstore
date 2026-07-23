#!/usr/bin/env bash
set -euo pipefail

command -v curl >/dev/null || { echo "curl is required"; exit 1; }
command -v jq >/dev/null || { echo "jq is required"; exit 1; }

BASE="${BASE:-http://127.0.0.1:8000/mcp/}"
PROTOCOL_VERSION="2025-06-18"
RUN_ID="ca110002"

SID=$(
  curl --http1.1 -sS -D - -o /dev/null \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"${PROTOCOL_VERSION}\",\"clientInfo\":{\"name\":\"persona-engineering-smoke\",\"version\":\"0.1\"},\"capabilities\":{}}}" \
    "$BASE" \
  | awk 'BEGIN{IGNORECASE=1} $1=="mcp-session-id:"{print $2}' \
  | tr -d '\r'
)
test -n "$SID" || { echo "MCP initialize did not return a session id"; exit 1; }

curl --http1.1 -sS \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "Mcp-Session-Id: $SID" \
  -H "MCP-Protocol-Version: $PROTOCOL_VERSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  "$BASE" >/dev/null

mcp_request() {
  local payload="$1"
  curl --http1.1 -sS -N \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -H "Mcp-Session-Id: $SID" \
    -H "MCP-Protocol-Version: $PROTOCOL_VERSION" \
    -d "$payload" \
    "$BASE" \
  | sed -n 's/^data: //p' \
  | head -n 1
}

TOOLS_JSON=$(mcp_request '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')
for tool in \
  jmeter_ping \
  jmeter_version \
  jmeter_list_plans \
  jmeter_run \
  jmeter_status \
  jmeter_run_details \
  jmeter_jtl_header \
  jmeter_artifact_manifest \
  jmeter_metrics_summary
do
  echo "$TOOLS_JSON" | jq -e --arg tool "$tool" \
    '.result.tools | any(.name == $tool)' >/dev/null
done

PING_JSON=$(mcp_request \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"jmeter_ping","arguments":{}}}')
echo "$PING_JSON" | jq -e \
  '.result.content[0].text | fromjson | .ok == true and .result.jmeter_available == true' \
  >/dev/null

RUN_REQUEST=$(jq -nc --arg run_id "$RUN_ID" '
  {
    jsonrpc: "2.0",
    id: 4,
    method: "tools/call",
    params: {
      name: "jmeter_run",
      arguments: {
        plan: "httpbin_smoke.jmx",
        run_id: $run_id,
        properties: {
          smoke_host: "127.0.0.1",
          smoke_port: "18080",
          smoke_protocol: "http",
          smoke_path: "/get"
        }
      }
    }
  }')
RUN_JSON=$(mcp_request "$RUN_REQUEST")
RUN_RESULT=$(echo "$RUN_JSON" | jq -c '.result.content[0].text | fromjson')
echo "$RUN_RESULT" | jq -e \
  '.schema_version == "pe.jmeter.mcp.v1" and .ok == true and .result.status == "completed"' \
  >/dev/null

STATUS_REQUEST=$(jq -nc --arg run_id "$RUN_ID" '
  {jsonrpc:"2.0",id:5,method:"tools/call",params:{name:"jmeter_status",arguments:{run_id:$run_id}}}')
STATUS_JSON=$(mcp_request "$STATUS_REQUEST")
STATUS_RESULT=$(echo "$STATUS_JSON" | jq -c '.result.content[0].text | fromjson')
echo "$STATUS_RESULT" | jq -e '.ok == true and .result.status == "completed"' >/dev/null

HEADER_REQUEST=$(jq -nc --arg run_id "$RUN_ID" '
  {jsonrpc:"2.0",id:6,method:"tools/call",params:{name:"jmeter_jtl_header",arguments:{run_id:$run_id}}}')
HEADER_JSON=$(mcp_request "$HEADER_REQUEST")
HEADER_RESULT=$(echo "$HEADER_JSON" | jq -c '.result.content[0].text | fromjson')
echo "$HEADER_RESULT" | jq -e \
  '.ok == true and (.result.columns | index("responseCode") != null)' >/dev/null

MANIFEST_REQUEST=$(jq -nc --arg run_id "$RUN_ID" '
  {jsonrpc:"2.0",id:7,method:"tools/call",params:{name:"jmeter_artifact_manifest",arguments:{run_id:$run_id}}}')
MANIFEST_JSON=$(mcp_request "$MANIFEST_REQUEST")
MANIFEST_RESULT=$(echo "$MANIFEST_JSON" | jq -c '.result.content[0].text | fromjson')
echo "$MANIFEST_RESULT" | jq -e '
  .ok == true and
  .result.schema_version == "pe.jmeter.evidence.v1" and
  ([.result.artifacts[] | select(.exists == true and (.sha256 | test("^[a-f0-9]{64}$")))] | length == 5)
' >/dev/null

METRICS_REQUEST=$(jq -nc --arg run_id "$RUN_ID" '
  {jsonrpc:"2.0",id:8,method:"tools/call",params:{name:"jmeter_metrics_summary",arguments:{run_id:$run_id}}}')
METRICS_JSON=$(mcp_request "$METRICS_REQUEST")
METRICS_RESULT=$(echo "$METRICS_JSON" | jq -c '.result.content[0].text | fromjson')
JTL_SHA=$(echo "$MANIFEST_RESULT" | jq -r '.result.artifacts.jtl.sha256')
echo "$METRICS_RESULT" | jq -e --arg jtl_sha "$JTL_SHA" '
  .ok == true and
  .result.schema_version == "pe.jmeter.metrics.v1" and
  .result.summary.sample_count == 1 and
  .result.summary.error_count == 0 and
  .result.source_jtl.sha256 == $jtl_sha
' >/dev/null

jq -n \
  --arg run_id "$RUN_ID" \
  --arg session_id "$SID" \
  --arg status "$(echo "$STATUS_RESULT" | jq -r '.result.status')" \
  '{
    ok: true,
    initiator: "persona-engineering-smoke",
    mcp_ordered: true,
    mcp_session_id: $session_id,
    adapter_schema: "pe.jmeter.mcp.v1",
    executor_schema: "pe.jmeter.cli.v1",
    evidence_schema: "pe.jmeter.evidence.v1",
    metrics_schema: "pe.jmeter.metrics.v1",
    run_id: $run_id,
    status: $status
  }'

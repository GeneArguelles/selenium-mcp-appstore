#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://jmeter-mcp-appstore-1.onrender.com}"

echo "== GET /jmeter/ping"
curl -sS "$BASE/jmeter/ping" | python -m json.tool

echo
echo "== GET /jmeter/version?raw=0"
curl -sS "$BASE/jmeter/version?raw=0" | python -m json.tool

echo
echo "== GET /jmeter/plans"
curl -sS "$BASE/jmeter/plans" | python -m json.tool

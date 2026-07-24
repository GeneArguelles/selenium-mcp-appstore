# selenium-mcp (ChatGPT Apps / MCP Server)

A **Model Context Protocol (MCP)** server that provides **session-based Selenium browser automation** over **Streamable HTTP**.

When deployed, ChatGPT (or any MCP client) connects to:

- `https://<your-domain>/mcp`

## What changed in this “store-ready” cleanup

This repo originally contained a FastAPI shim with custom endpoints like `/mcp/schema` and `/mcp/invoke`.
For Apps SDK / modern MCP clients, you want a **real MCP server**.

This repo now includes `mcp_server_v2.py`, built on the **official MCP Python SDK (FastMCP)**.

## Tools exposed

All tools are **session-based** (create a session once, then perform multiple steps in the same browser):

- `create_session()` → `{ session_id }`
- `open_page(session_id, url, wait_css?, timeout_s?)`
- `click(session_id, css_selector, timeout_s?)`
- `type_text(session_id, css_selector, text, clear_first?, timeout_s?)`
- `get_text(session_id, css_selector, timeout_s?)`
- `screenshot(session_id)` → base64 PNG
- `close_session(session_id)`
- `reap_idle_sessions(max_idle_seconds?)`

The server also exposes policy-constrained Persona Engineering performance tools:

- `jmeter_ping()`
- `jmeter_version(include_raw?)`
- `jmeter_list_plans()`
- `jmeter_run(plan, run_id?, properties?)`
- `jmeter_status(run_id)`
- `jmeter_run_details(run_id)`
- `jmeter_jtl_header(run_id)`
- `jmeter_artifact_manifest(run_id)`
- `jmeter_metrics_summary(run_id)`

These tools invoke the isolated executor as a separate process and return the
versioned `pe.jmeter.mcp.v1` response contract. They do not accept arbitrary
executables, filesystem paths, environment variables, target URLs, or raw JMeter
arguments.

## JMeter executor CLI

The repository also contains a policy-constrained JMeter executor intended for
Persona Engineering orchestration. Its automation interface emits one versioned
JSON object per invocation:

```bash
python -m jmeter_executor ping
python -m jmeter_executor list-plans
python -m jmeter_executor run --plan httpbin_smoke.jmx
python -m jmeter_executor status --run-id <run_id>
```

See `jmeter_executor/README.md` for the JSON contract, configuration boundary,
exit codes, security invariants, and Docker smoke-test instructions.

The checked-in `blazedemo_booking_smoke.jmx` plan provides an opt-in, bounded
four-step booking smoke test for `https://blazedemo.com`. Its CI validation uses
a local fixture and sends no routine workflow traffic to the public site. See
`jmeter_executor/BLAZEDEMO_SMOKE_RUNBOOK.md` for the governed Persona
Engineering execution procedure and assessment policy.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Runs Streamable HTTP MCP at http://localhost:8000/mcp
python mcp_server_v2.py
```

Optional env vars:

- `PORT` (default `8000`)
- `HOST` (default `0.0.0.0`)
- `CHROME_BINARY` (if Chrome isn’t on PATH)
- `CHROMEDRIVER_PATH` (if chromedriver isn’t on PATH)
- `JMETER_PROJECT_ROOT` (defaults to this repository)
- `JMETER_BIN` (defaults to `jmeter`)
- `JMETER_TIMEOUT_SECONDS` (executor timeout; default `600`)
- `JMETER_MCP_TIMEOUT_SECONDS` (adapter timeout; defaults to executor timeout + 30)
- `JMETER_ALLOWED_PROPERTIES` (comma-separated deployment policy)

## Deploy

Deploy behind HTTPS (Render/Fly/Railway/Cloud Run). The **MCP endpoint must be stable**:

- `https://<your-domain>/mcp`

This repo includes a `Procfile` that runs:

- `python mcp_server_v2.py`

> Note: for production, install Chrome + chromedriver in your container/runtime.

## How to test (smoke)

This repo includes a curl-based MCP smoke test that:
- initializes an MCP session
- lists tools
- creates a Selenium browser session
- opens https://example.com, verifies the `h1`
- takes a screenshot (`smoke.png`)
- closes the browser session

The JMeter CI workflow also starts the FastMCP server, identifies its client as
`persona-engineering-smoke`, orders a checked-in plan through `jmeter_run`, and
queries the resulting status and JTL header through MCP. This proves MCP ordering;
ledger, assessor, and normalized reporting integration remain separate milestones.

### Prereqs
- `bash`
- `curl`
- `jq`
- `base64`

### Run
```bash
chmod +x smoke_mcp.sh
./smoke_mcp.sh
```

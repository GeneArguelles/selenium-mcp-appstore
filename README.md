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

### Prereqs
- `bash`
- `curl`
- `jq`
- `base64`

### Run
```bash
chmod +x smoke_mcp.sh
./smoke_mcp.sh


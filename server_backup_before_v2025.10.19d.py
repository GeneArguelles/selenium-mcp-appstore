#!/usr/bin/env python3
# ==========================================================
# Selenium MCP Server (Render-ready, full diagnostics)
# Version: 2025.10.19d — Stable Production Baseline
# ==========================================================

import os
import time
import platform
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# ==========================================================
# Globals
# ==========================================================
SERVER_NAME = "Selenium"
SERVER_DESC = "MCP server providing headless browser automation via Selenium."
APP_START_TIME = time.time()

CHROMEDRIVER_PATH = "./chromedriver/chromedriver"
CHROME_BINARY = os.getenv("CHROME_BINARY", "/opt/render/project/src/.local/chrome/chrome-linux/chrome")

# ==========================================================
# FastAPI Init + CORS
# ==========================================================
app = FastAPI(title=f"{SERVER_NAME} MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, tighten if necessary
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# ==========================================================
# MCP Manifest Builder
# ==========================================================
def build_mcp_manifest():
    """Return a fully MCP-compliant manifest shared by all endpoints."""
    manifest = {
        "version": "2025-10-02",
        "type": "mcp",
        "server_info": {
            "name": SERVER_NAME,
            "description": SERVER_DESC,
            "version": "1.0.0",
            "runtime": platform.python_version(),
        },
        "capabilities": {
            "invocation": True,
            "streaming": False,
            "multi_tool": False,
        },
        "tools": [
            {
                "name": "selenium_open_page",
                "description": "Open a URL in a headless Chrome browser and return the page title.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            }
        ],
    }
    return manifest

# ==========================================================
# Root Manifest (GET + POST + HEAD + OPTIONS)
# ==========================================================
@app.api_route("/", methods=["GET", "POST", "HEAD", "OPTIONS"])
def root_manifest():
    """Primary root manifest for MCP discovery (Agent Builder handshake)."""
    print("[INFO] Served root manifest via GET/POST/HEAD/OPTIONS")
    manifest = build_mcp_manifest()

    response = JSONResponse(content=manifest)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Content-Type"] = "application/json"
    return response

# ==========================================================
# /health — Diagnostic and uptime probe
# ==========================================================
@app.get("/health")
def health_check():
    uptime = round(time.time() - APP_START_TIME, 2)
    chrome_ok = os.path.exists(CHROME_BINARY)
    status = "healthy" if chrome_ok else "unhealthy"
    phase = "ready" if chrome_ok else "init"

    print(f"[INFO] /health → {status}, uptime {uptime}s, chrome_ok={chrome_ok}")

    return {
        "status": status,
        "phase": phase,
        "uptime_seconds": uptime,
        "chrome_path": CHROME_BINARY,
    }

# ==========================================================
# /mcp/schema — Canonical MCP schema
# ==========================================================
@app.api_route("/mcp/schema", methods=["GET", "POST", "OPTIONS"])
def mcp_schema():
    """Canonical MCP schema (used by Agent Builder for tool registration)."""
    manifest = build_mcp_manifest()
    print("[INFO] Served /mcp/schema manifest (canonical)")

    response = JSONResponse(content=manifest)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Content-Type"] = "application/json"
    return response

# ==========================================================
# /live — Cache-bypass alias for /mcp/schema
# ==========================================================
@app.api_route("/live", methods=["GET", "POST", "OPTIONS"])
def mcp_live():
    """
    Cache-bypass endpoint for forcing Agent Builder revalidation.
    Supports GET/POST/OPTIONS and returns a fresh manifest each time.
    """
    print("[INFO] Served /live alias (cache-buster)")

    manifest = build_mcp_manifest()
    manifest["message"] = "Live manifest refresh triggered."
    manifest["schema_url"] = "/mcp/schema"

    response = JSONResponse(content=manifest)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Content-Type"] = "application/json"
    return response

# ==========================================================
# Pydantic model for /mcp/invoke requests
# ==========================================================
class InvokeRequest(BaseModel):
    tool: str
    arguments: dict

# ==========================================================
# /mcp/invoke — Executes a Selenium automation command
# ==========================================================
@app.post("/mcp/invoke")
def invoke_tool(req: InvokeRequest):
    print(f"[INFO] Invoked tool: {req.tool}")

    if req.tool == "selenium_open_page":
        url = req.arguments.get("url")
        if not url:
            return JSONResponse(status_code=400, content={"error": "Missing URL argument"})

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.binary_location = CHROME_BINARY

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            title = driver.title
            driver.quit()
            return {"result": f"Opened {url}", "title": title}
        except Exception as e:
            print(f"[ERROR] Selenium invoke error: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})

    return JSONResponse(status_code=400, content={"error": f"Unknown tool: {req.tool}"})

# ==========================================================
# Allow OPTIONS preflights globally
# ==========================================================
@app.options("/{full_path:path}")
def options_handler(full_path: str):
    return JSONResponse(status_code=204, content=None)

# ==========================================================
# Startup Event (for Render logs)
# ==========================================================
@app.on_event("startup")
def startup_log():
    print("==========================================================")
    print(f"[INFO] Starting {SERVER_NAME} MCP Server...")
    print(f"[INFO] Description: {SERVER_DESC}")
    print(f"[INFO] Version: 1.0.0")
    print(f"[INFO] Python Runtime: {platform.python_version()}")
    print(f"[INFO] Chrome Binary: {CHROME_BINARY}")
    print(f"[INFO] ChromeDriver Path: {CHROMEDRIVER_PATH}")
    print("==========================================================")
    print(f"[INFO] Selenium MCP startup complete.")

# ==========================================================
# Local execution entry point (for testing)
# ==========================================================
if __name__ == "__main__":
    import uvicorn
    print("[INFO] Launching Uvicorn directly on port 10000...")
    uvicorn.run("server:app", host="0.0.0.0", port=10000, reload=True)

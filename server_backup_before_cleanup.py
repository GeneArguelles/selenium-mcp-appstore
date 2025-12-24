# ==========================================================
# Selenium MCP Server — Render-Ready (v2025.10.18a)
# Python 3.11 / FastAPI 0.119 / Headless Chrome
# ==========================================================

import os
import time
import platform
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# ==========================================================
# Globals
# ==========================================================
APP_START_TIME = time.time()
SERVER_NAME = "Selenium"
SERVER_DESC = "MCP server providing headless browser automation via Selenium."
CHROME_BINARY = os.getenv("CHROME_BINARY", "/opt/render/project/src/.local/chrome/chrome-linux/chrome")
CHROMEDRIVER_PATH = "./chromedriver/chromedriver"


# ==========================================================
# Chrome Binary Resolver (Render vs Local)
# ==========================================================
import platform
import shutil
import os

def resolve_chrome_binary():
    """
    Returns a Chrome binary path that works for both Render and local machines.
    """
    # Render’s path
    render_path = "/opt/render/project/src/.local/chrome/chrome-linux/chrome"
    if os.path.exists(render_path):
        return render_path

    # macOS default installation paths
    mac_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for path in mac_paths:
        if os.path.exists(path):
            return path

    # Linux typical locations
    for path in ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]:
        if shutil.which(path):
            return path

    print("[WARN] ⚠️ Chrome binary not found — relying on system default PATH")
    return shutil.which("google-chrome") or shutil.which("chromium") or "chrome"
    

CHROME_BINARY = resolve_chrome_binary()
print(f"[INFO] Chrome binary resolved as: {CHROME_BINARY}")


# ==========================================================
# FastAPI Init + CORS
# ==========================================================
app = FastAPI(title=f"{SERVER_NAME} MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production: ["https://agentbuilder.openai.com"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ==========================================================
# Root Manifest (GET + POST)
# ==========================================================
from fastapi.responses import JSONResponse

@app.api_route("/", methods=["GET", "POST"])
def root_manifest():
    """
    Root manifest for OpenAI Agent Builder discovery.
    Responds with the MCP-compliant manifest that lists server capabilities and tools.
    """
    print("[INFO] Served root manifest via GET/POST")

    manifest = {
        "version": "2025-10-01",
        "type": "mcp_server",
        "server_info": {
            "type": "mcp_server",
            "name": "Selenium",
            "description": "MCP server providing headless browser automation via Selenium.",
            "version": "1.0.0",
            "runtime": platform.python_version(),
            "capabilities": {
                "invocation": True,
                "streaming": False,
                "multi_tool": False,
            },
        },
        "tools": [
            {
                "name": "selenium_open_page",
                "description": "Open a URL in a headless Chrome browser and return the page title.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"}
                    },
                    "required": ["url"]
                }
            }
        ]
    }

    return JSONResponse(content=manifest)


# ==========================================================
# Models
# ==========================================================
class SchemaResponse(BaseModel):
    version: str
    type: str
    server_info: dict
    capabilities: dict
    tools: list | None = None

class InvokeRequest(BaseModel):
    tool: str
    arguments: dict

# ==========================================================
# Health Check
# ==========================================================
@app.get("/health")
def health_check():
    uptime = round(time.time() - APP_START_TIME, 2)
    chrome_ok = os.path.exists(CHROME_BINARY)
    return {
        "status": "healthy" if chrome_ok else "unhealthy",
        "phase": "ready" if chrome_ok else "init",
        "uptime_seconds": uptime,
        "chrome_path": CHROME_BINARY,
    }

# ==========================================================
# MCP Manifest Template
# ==========================================================
def base_manifest():
    return {
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
    }

# ==========================================================
# Root Manifest (GET + POST)
# ==========================================================
@app.api_route("/", methods=["GET", "POST"])
def root_manifest():
    print("[INFO] Served root manifest via GET/POST")
    manifest = base_manifest()
    manifest["schema_url"] = "/mcp/schema"
    return JSONResponse(content=manifest)

# ==========================================================
# /live — Cache-buster alias
# ==========================================================
@app.get("/live")
def live_manifest():
    print("[INFO] Served /live alias (cache-buster)")
    manifest = base_manifest()
    manifest["schema_url"] = "/mcp/schema"
    manifest["message"] = "Live endpoint reached — manifest refresh triggered."
    return JSONResponse(content=manifest)

# ==========================================================
# /mcp/schema — Tool Schema
# ==========================================================
@app.api_route("/mcp/schema", methods=["GET", "POST", "OPTIONS"])
def get_schema():
    print("[INFO] Served /mcp/schema")
    schema = base_manifest()
    schema["tools"] = [
        {
            "name": "selenium_open_page",
            "description": "Open a URL in a headless Chrome browser and return the page title.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        }
    ]
    return JSONResponse(content=schema)

# ==========================================================
# /mcp/invoke — Execute tool
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
            return JSONResponse(status_code=500, content={"error": str(e)})

    return JSONResponse(status_code=400, content={"error": f"Unknown tool: {req.tool}"})

# ==========================================================
# OPTIONS Preflight Handler
# ==========================================================
@app.options("/{full_path:path}")
def options_handler(full_path: str):
    print(f"[INFO] OPTIONS preflight for /{full_path}")
    return PlainTextResponse("OK", status_code=200)

# ==========================================================
# Startup Logs
# ==========================================================
@app.on_event("startup")
def startup_banner():
    print("==========================================================")
    print(f"[INFO] Starting {SERVER_NAME} MCP Server...")
    print(f"[INFO] Description: {SERVER_DESC}")
    print(f"[INFO] Version: 1.0.0")
    print(f"[INFO] Python Runtime: {platform.python_version()}")
    print(f"[INFO] Chrome Binary: {CHROME_BINARY}")
    print(f"[INFO] ChromeDriver Path: {CHROMEDRIVER_PATH}")
    print("==========================================================")
    print("[INFO] Selenium MCP startup complete.")


# ==========================================================
# Local execution entry point (for local testing)
# ==========================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    print(f"[INFO] Launching Uvicorn directly on port {port}...")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )

#!/usr/bin/env python3
# ==========================================================
# Selenium MCP — Headless Browser Automation (FastAPI MCP)
# Version: v20251027-FULL
# Author: Gene Arguelles, LLC
# ==========================================================
import os, datetime, string, platform, logging
import subprocess

# ----------------------------------------------------------
# ✅ Canonical MCP_VERSION bootstrap
# Ensures deterministic version tag across all workers
# ----------------------------------------------------------
if "MCP_VERSION" not in globals() or not globals().get("MCP_VERSION"):
    MCP_VERSION = os.getenv(
        "MCP_VERSION",
        f"v{datetime.date.today().strftime('%Y%m%d')}a"
    )
    print(f"[BOOT] MCP_VERSION pre-initialized as {MCP_VERSION}")

if not isinstance(MCP_VERSION, str) or not MCP_VERSION.startswith("v"):
    MCP_VERSION = f"v{datetime.date.today().strftime('%Y%m%d')}a"
    print(f"[BOOT] MCP_VERSION repaired to {MCP_VERSION}")

print(f"[INFO] Launching MCP Server (version={MCP_VERSION})")

import json     # ✅ Add this once here
import openai
import platform
import sys
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_tools import (
    selenium_open_page,
    selenium_click,
    selenium_get_text,
    selenium_screenshot,
)
from dotenv import load_dotenv
load_dotenv('/etc/secrets/.env')

# ----------------------------------------------------------
# 🌐 Global MCP Version Utility with Auto-Increment + Logging
# ----------------------------------------------------------

def _generate_mcp_version() -> str:
    """Generate an MCP version string like v20251028a, v20251028b, etc."""
    base_date = datetime.date.today().strftime('%Y%m%d')
    env_version = os.getenv("MCP_VERSION")  # explicit override
    env_suffix = os.getenv("MCP_SUFFIX")    # manual suffix (e.g., b, c, d)
    version_file = "mcp_version.txt"
    base_prefix = f"v{base_date}"

    # Priority 1: explicit environment variable
    if env_version:
        print(f"[INFO] MCP version explicitly set via environment → {env_version}")
        return env_version

    # Determine next suffix
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            last_version = f.read().strip()
        if last_version.startswith(base_prefix):
            last_suffix = last_version[-1]
            if last_suffix in string.ascii_lowercase:
                next_suffix = string.ascii_lowercase[
                    (string.ascii_lowercase.index(last_suffix) + 1) % len(string.ascii_lowercase)
                ]
            else:
                next_suffix = "a"
            new_version = f"{base_prefix}{next_suffix}"
        else:
            new_version = f"{base_prefix}a"
    else:
        new_version = f"{base_prefix}a"

    # Manual override via MCP_SUFFIX (e.g., MCP_SUFFIX=c)
    if env_suffix:
        new_version = f"{base_prefix}{env_suffix}"
        print(f"[INFO] MCP_SUFFIX override detected → {env_suffix}")

    # Save to file for next deploy
    with open(version_file, "w") as f:
        f.write(new_version)

    # Log in Render output for visibility
    print(f"[INFO] MCP version updated to {new_version}")

    return new_version


# Initialize MCP version globally
MCP_VERSION = _generate_mcp_version()

def get_mcp_version() -> str:
    """Return the canonical MCP version string (never None)."""
    return MCP_VERSION or "v0.0.0-unknown"

print(f"[BOOT] MCP_VERSION initialized → {MCP_VERSION}")


# ==========================================================
# === Banner ===
# ==========================================================
def startup_debug_banner():
    import datetime
    print(f"🚀 Render rebuild verified: {datetime.datetime.now().isoformat()} | MCP_VERSION: {get_mcp_version()}", flush=True)

startup_debug_banner()

# ----------------------------------------------------------
# Imports and FastAPI app setup
# ----------------------------------------------------------
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()

# 🌐 CORS Middleware Configuration ...
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (like logo.png)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to OpenAI IPs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# Global constants — must be defined before route declarations
# ==========================================================
SERVER_NAME = "Selenium MCP"
SERVER_DESC = "Headless browser automation tools for OpenAI Agent Builder."
CHROME_BINARY = "/opt/render/project/src/.local/chrome/chrome-linux/chrome"
BASE_URL = os.getenv("BASE_URL", "https://selenium-mcp.onrender.com")

# ==========================================================
# Force cache busting on Render build layer
# ==========================================================
FORCE_REBUILD_TAG = "v20251027b"  # ⬅️ bump this every time you need a new container
print(f"[BOOT] FORCE_REBUILD_TAG = {FORCE_REBUILD_TAG}")

# ==========================================================
# Failsafe: Ensure MCP_VERSION always initialized at import
# ==========================================================
# ----------------------------------------------------------
# Root manifest endpoint (for OpenAI Agent Builder)
# ----------------------------------------------------------
@app.get("/")
def root_manifest():
    return {
        "type": "manifest",
        "name": SERVER_NAME,
        "description": SERVER_DESC,
        "version": get_mcp_version()
    }

# ----------------------------------------------------------
# MCP Manifest Endpoint (GET + POST)
# ----------------------------------------------------------
MCP_MANIFEST = {
    "type": "mcp_server",
    "schema_version": "v1",
    "name_for_human": SERVER_NAME,
    "name_for_model": "selenium",
    "description_for_human": SERVER_DESC,
    "description_for_model": "MCP server exposing Selenium tools: open_page, click, text, screenshot.",
    "auth": {"type": "none"},
    "api": {"type": "json", "url": f"{BASE_URL}/mcp/schema"},
    "logo_url": f"{BASE_URL}/static/logo.png",
    "contact_email": "youremail@example.com",
    "legal_info_url": f"{BASE_URL}/legal",
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "selenium_open_page",
                "description": "Open a URL in a headless Chrome browser and return the page title.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The full URL of the page to open (including https://)."
                        }
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "selenium_click",
                "description": "Click an element on the page using a CSS selector.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "The CSS selector for the element to click."
                        }
                    },
                    "required": ["selector"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "selenium_screenshot",
                "description": "Take a screenshot and save it to a file. Returns the local path to the screenshot.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The desired filename (with .png extension) to save the screenshot."
                        }
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "selenium_get_text",
                "description": "Retrieve visible text content from the page using a CSS selector.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "The CSS selector for the element to extract text from."
                        }
                    },
                    "required": ["selector"]
                }
            }
        }
    ],
}

@app.get("/mcp/manifest")
@app.post("/mcp/manifest")
async def get_manifest(request: Request):
    print(f"[INFO] /mcp/manifest served successfully ({len(MCP_MANIFEST['tools'])} tools)")
    return JSONResponse(content=MCP_MANIFEST)

# ----------------------------------------------------------
# Health Check — Required for Render Liveness Check
# ----------------------------------------------------------
@app.get("/health")
def health_check():
    """
    Lightweight liveness check used by Render platform
    """
    return {"status": "ok"}

# ----------------------------------------------------------
# MCP_TOOLS_LIST (Strict OpenAI Function Schema)
# ----------------------------------------------------------
MCP_TOOLS_LIST = [
    {
        "type": "function",
        "function": {
            "name": "selenium_open_page",
            "description": "Open a URL in a headless Chrome browser and return the page title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the page to open (including https://)."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "selenium_click",
            "description": "Click an element on the page using a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "The CSS selector for the element to click."
                    }
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "selenium_screenshot",
            "description": "Take a screenshot and save it to a file. Returns the local path to the screenshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The desired filename (with .png extension) to save the screenshot."
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "selenium_get_text",
            "description": "Retrieve visible text content from the page using a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "The CSS selector for the element to extract text from."
                    }
                },
                "required": ["selector"]
            }
        }
    }
]

@app.post("/mcp/schema")
def serve_adaptive_schema(request: Request):
    client_ua = request.headers.get("User-Agent", "unknown")
    print(f"[SCHEMA] Request from: {client_ua}")
    return {
        "version": get_mcp_version(),
        "tools": MCP_TOOLS_LIST
    }

TOOL_EXECUTION_MAP = {
    "selenium_open_page": "handle_open_page"
}

# ==========================================================
# GET files
# ==========================================================
@app.get("/files")
def get_file(path: str):
    """
    Secure file fetch for artifacts written to /tmp (e.g., screenshots).
    Usage: /files?path=/tmp/screenshot-xxxx.png
    """
    # Only allow /tmp
    if not path.startswith("/tmp/"):
        raise HTTPException(status_code=400, detail="Only /tmp files are allowed")

    # Only allow PNGs
    if not path.endswith(".png"):
        raise HTTPException(status_code=400, detail="Only .png files are allowed")

    # Must exist
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type="image/png", filename=os.path.basename(path))

# ==========================================================
# OpenAI MCP Manifest (Agent Builder discovery compatible)
# ==========================================================
@app.get("/mcp/manifest")
def serve_manifest():
    """
    Always-safe manifest route for OpenAI Agent Builder discovery.
    Never throws; logs detailed errors to Render console.
    """
    from fastapi.responses import JSONResponse

    try:
        tools = MCP_TOOLS_LIST if "MCP_TOOLS_LIST" in globals() else []
        manifest = {
            "type": "mcp_server",
            "schema_version": "v1",
            "name_for_human": "Selenium MCP",
            "name_for_model": "selenium",
            "description_for_human": (
                "Headless browser automation tools for OpenAI Agent Builder. "
                "Provides Selenium-based methods for opening pages, clicking elements, "
                "extracting text, and taking screenshots."
            ),
            "description_for_model": (
                "MCP server exposing Selenium tools: open_page, click, text, screenshot."
            ),
            "auth": {"type": "none"},
            "api": {
                "type": "json",
                "url": "https://selenium-mcp.onrender.com/mcp/schema"
            },
            "logo_url": "https://selenium-mcp.onrender.com/static/logo.png",
            "contact_email": "youremail@example.com",
            "legal_info_url": "https://selenium-mcp.onrender.com/legal",
            "tools": tools
        }
        print(f"[INFO] /mcp/manifest served successfully ({len(tools)} tools)")
        return JSONResponse(content=manifest)

    except Exception as e:
        # Log and fail gracefully
        import traceback
        tb = traceback.format_exc()
        print(f"[ERROR] /mcp/manifest exception: {e}\n{tb}")
        return JSONResponse(
            content={
                "error": "Manifest generation failed",
                "details": str(e),
                "trace": tb
            },
            status_code=500
        )


# ==========================================================
# Static Manifest Alias (/static/manifest.json)
# ==========================================================
@app.get("/static/manifest.json")
def serve_static_manifest():
    """
    Serve a stable manifest for external agents (Render-safe).
    Embeds tool definitions inline to avoid missing globals.
    """
    print(f"[INFO] Served /static/manifest.json → mirrors /mcp/schema ({get_mcp_version()})")

    # Inline tool list to ensure no async import issues
    tools = [
        {
            "name": "selenium_open_page",
            "description": "Open a URL in a headless Chrome browser and return the page title.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "selenium_click",
            "description": "Click an element by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
        {
            "name": "selenium_text",
            "description": "Get text content by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
        {
            "name": "selenium_screenshot",
            "description": "Save a PNG screenshot to /tmp and return its path.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
    ]

    schema = {
        "type": "mcp_server",
        "version": get_mcp_version(),
        "mcp_version": get_mcp_version(),
        "server_info": {
            "name": SERVER_NAME,
            "description": SERVER_DESC,
            "version": get_mcp_version(),
            "runtime": platform.python_version(),
        },
        "capabilities": {
            "invocation": True,
            "streaming": False,
            "multi_tool": False,
        },
        "tools": tools,
    }

    return JSONResponse(
        content=schema,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Content-Disposition": 'inline; filename="manifest.json"',
        },
    )


# ==========================================================
# MCP Static Manifest (Safe path alias)
# ==========================================================
@app.get("/mcp/manifest")
def serve_mcp_manifest():
    """
    Serve version-pinned manifest for MCP discovery.
    Uses /mcp/manifest instead of /static/manifest.json
    to avoid FastAPI StaticFiles conflicts.
    """
    print(f"[INFO] Served /mcp/manifest → stable schema export ({get_mcp_version()})")

    tools = [
        {
            "name": "selenium_open_page",
            "description": "Open a URL in a headless Chrome browser and return the page title.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "selenium_click",
            "description": "Click an element by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
        {
            "name": "selenium_text",
            "description": "Get text content by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
        {
            "name": "selenium_screenshot",
            "description": "Save a PNG screenshot to /tmp and return its path.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
    ]

    schema = {
        "type": "mcp_server",
        "version": get_mcp_version(),
        "mcp_version": get_mcp_version(),
        "server_info": {
            "name": SERVER_NAME,
            "description": SERVER_DESC,
            "version": get_mcp_version(),
            "runtime": platform.python_version(),
        },
        "capabilities": {
            "invocation": True,
            "streaming": False,
            "multi_tool": False,
        },
        "tools": tools,
    }

    return JSONResponse(
        content=schema,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Content-Disposition": 'inline; filename="manifest.json"',
        },
    )


# ----------------------------------------------------------
# Invocation Schema Input Model
# ----------------------------------------------------------
class InvokeRequest(BaseModel):
    tool: str
    arguments: dict | None = None

# ==========================================================
# Root Manifest (for MCP discovery)
# ==========================================================
@app.get("/")
def root_manifest(request: Request):
    return {
        "type": "mcp_server",
        "mcp_version": get_mcp_version(),
        "version": get_mcp_version(),
        "server_info": {
            "name": SERVER_NAME,
            "description": SERVER_DESC,
            "version": get_mcp_version(),
        },
        "endpoints": {
            "schema": f"{request.base_url}mcp/schema",
            "live": f"{request.base_url}live"
        }
    }


# ----------------------------------------------------------
# POST Root — Return manifest (for Agent Builder)
# ----------------------------------------------------------
@app.post("/")
def post_root_manifest(request: Request):
    return {
        "type": "mcp_server",
        "mcp_version": get_mcp_version(),
        "version": get_mcp_version(),
        "server_info": {
            "name": SERVER_NAME,
            "description": SERVER_DESC,
           "version": get_mcp_version(),
        },
        "endpoints": {
            "schema": f"{request.base_url}mcp/schema",
            "live": f"{request.base_url}live",
        },
    }

# ----------------------------------------------------------
# Live Check — Lightweight Ping
# ----------------------------------------------------------
@app.api_route("/live", methods=["GET", "POST"])
def live():
    return {"status": "live", "version": get_mcp_version()}


# ----------------------------------------------------------
# MCP Schema — Strictly Formatted Tool List for Agents
# ----------------------------------------------------------
@app.api_route("/mcp/schema", methods=["GET", "POST", "HEAD", "OPTIONS"])
def serve_schema(request: Request):
    """Serve unified schema structure for OpenAI Agent Builder (dual-mode: full MCP or flattened AB schema)."""
    import os, platform, json, logging, sys, datetime
    from copy import deepcopy
    from fastapi.responses import Response

    print(f"🧩 [CHECKPOINT] serve_schema() invoked fresh at {datetime.datetime.now().isoformat()}", flush=True)
    sys.stdout.flush()

    # ----------------------------------------------------------
    # Defensive: Clear old schema shadow if any
    # ----------------------------------------------------------
    if "schema" in globals():
        try:
            del globals()["schema"]
        except Exception:
            pass

    # ----------------------------------------------------------
    # Resolve version deterministically
    # ----------------------------------------------------------
    resolved_version = str(get_mcp_version() or "v0.0.0-dev")

    # ----------------------------------------------------------
    # Canonical MCP schema (full structure)
    # ----------------------------------------------------------
    schema = {
        "type": "mcp_server",
        "version": resolved_version,
        "mcp_version": resolved_version,
        "server_info": {
            "name": SERVER_NAME,
            "description": SERVER_DESC,
            "version": resolved_version,
            "runtime": platform.python_version(),
        },
        "capabilities": {
            "invocation": True,
            "streaming": False,
            "multi_tool": False,
        },
        "tools": MCP_TOOLS_LIST,
    }

    # ----------------------------------------------------------
    # Literal safety enforcement
    # ----------------------------------------------------------
    def literalize(obj):
        if isinstance(obj, dict):
            return {k: literalize(v) for k, v in obj.items()}
        elif obj is None:
            return "v0.0.0-dev"
        return str(obj)

    schema = literalize(schema)

    # 🧠 Ensure 'tools' array is valid JSON
    import ast
    if isinstance(schema.get("tools"), str):
        try:
            schema["tools"] = ast.literal_eval(schema["tools"])
            print(f"🧠 [CHECKPOINT] Tools re-parsed into JSON array ({len(schema['tools'])} items)", flush=True)
        except Exception as e:
            print(f"⚠️ [WARN] Tools list could not be parsed: {e}", flush=True)
            schema["tools"] = []

    # 🩹 Version repairs
    resolved_version = get_mcp_version()
    schema["mcp_version"] = schema.get("mcp_version") or resolved_version
    if "server_info" in schema:
        schema["server_info"]["version"] = schema["server_info"].get("version") or resolved_version

    # ----------------------------------------------------------
    # 🧠 AUTO-DETECT CLIENT TYPE
    # ----------------------------------------------------------
    accept = (request.headers.get("accept", "") or "").lower().replace("+", "").replace("/", "")
    user_agent = (request.headers.get("user-agent", "") or "").lower().replace("+", "").replace("/", "")
    is_agentbuilder = any(
        token in accept or token in user_agent
        for token in ["agentbuilder", "openaiagentbuilder", "vndagentbuilderjson"]
    )

    print(f"🧩 [CHECKPOINT] Agent Builder detection → accept='{accept}' | user_agent='{user_agent}' | result={is_agentbuilder}", flush=True)

    # ----------------------------------------------------------
    # Alternate flattened schema (for OpenAI Agent Builder)
    # ----------------------------------------------------------
    flattened_schema = {
        "mcp_version": "1.0",
        "name": "selenium_mcp",
        "description": "Headless browser automation tools for OpenAI Agent Builder.",
        "tools": [
            {
                "name": "selenium_open_page",
                "description": "Open a URL in a headless Chrome browser and return the page title.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Full URL including https://"}
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "selenium_click",
                "description": "Click an element using a CSS selector.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector for the element to click."}
                    },
                    "required": ["selector"],
                },
            },
            {
                "name": "selenium_screenshot",
                "description": "Take a screenshot and return the saved file path.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Filename (with .png extension)."}
                    },
                    "required": ["filename"],
                },
            },
            {
                "name": "selenium_get_text",
                "description": "Retrieve visible text from an element.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector for the element."}
                    },
                    "required": ["selector"],
                },
            },
        ],
    }

    # ----------------------------------------------------------
    # Choose which schema to return
    # ----------------------------------------------------------
    selected_schema = flattened_schema if is_agentbuilder else schema

    payload = deepcopy(selected_schema)
    full_json = json.dumps(payload, indent=2, ensure_ascii=False)
    parsed_json = json.loads(full_json)
    safe_json = json.loads(json.dumps(parsed_json, default=str))

    # ----------------------------------------------------------
    # ✅ MCP Schema Hardening (ensures literal arrays and proper headers)
    # ----------------------------------------------------------
    if isinstance(safe_json.get("tools"), str):
        import ast
        try:
            safe_json["tools"] = ast.literal_eval(safe_json["tools"])
        except Exception:
            safe_json["tools"] = []
    safe_json["type"] = "mcp_server"

    # ----------------------------------------------------------
    # Final reporting
    # ----------------------------------------------------------
    print(
        f"🚀 [FINAL-RETURN] Returning {'AgentBuilder' if is_agentbuilder else 'Full MCP'} schema | "
        f"Version={resolved_version} | Tools={len(safe_json.get('tools', []))}",
        flush=True,
    )

    # ----------------------------------------------------------
    # ✅ Response Hardening (adds proper MIME + CORS + Content-Length)
    # ----------------------------------------------------------
    final_json_str = json.dumps(safe_json, ensure_ascii=False, indent=2)
    return Response(
        content=final_json_str,
        media_type="application/json",
        headers={
            "Content-Length": str(len(final_json_str.encode("utf-8"))),
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


# ----------------------------------------------------------
# MCP Status — Lightweight Health & Compliance Check
# ----------------------------------------------------------
@app.get("/mcp/status")
def mcp_status():
    """Return simple MCP readiness & compliance status for remote checks."""
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "status": "ok",
        "message": "Selenium MCP server is live and compliant.",
        "mcp_version": get_mcp_version(),
        "tools_registered": len(MCP_TOOLS_LIST),
    })

# ----------------------------------------------------------
# Internal Debug Route — Reveals active MCP schema & tools
# ----------------------------------------------------------
@app.get("/mcp/internal_schema")
def internal_schema():
    try:
        return {
            "type": "mcp_server",
            "version": "v1",
            "server_name": "selenium-mcp",
            "description": "Internal diagnostic route exposing the active MCP tools list.",
            "manifest_schema": {
                "schema_type": "openai_manifest",
                "schema_version": "v1",
                "endpoint": f"{BASE_URL}/mcp/schema"
            },
            "tools_registered": len(MCP_TOOLS_LIST),
            "tool_names": [tool["name"] for tool in MCP_TOOLS_LIST],
            "tools": MCP_TOOLS_LIST
        }
    except Exception as e:
        return {
            "error": "Failed to load MCP internal schema.",
            "details": str(e)
        }


# ----------------------------------------------------------
# openapi.yaml route
# ----------------------------------------------------------
@app.get("/openapi.yaml")
def openapi_spec():
    return Response(yaml.dump({
        "openapi": "3.0.0",
        "info": {
            "title": "Selenium MCP API",
            "version": get_mcp_version(),
            "description": "OpenAPI spec for Selenium MCP tools"
        },
        "paths": { ... }  # define your 4 tools here
    }), media_type="application/x-yaml")


# ----------------------------------------------------------
# MCP POST fallback
# ----------------------------------------------------------
@app.post("/mcp/schema")
def post_schema():
    """
    Graceful POST fallback for schema endpoint.
    Agent Builder or other clients may probe via POST.
    """
    return get_schema()


# ----------------------------------------------------------
# 🧠 MCP Invocation Endpoint — active dispatcher (MCP-compliant)
# ----------------------------------------------------------
@app.post("/mcp/invoke")
async def mcp_invoke(request: Request):
    """
    Handles invocation requests from Agent Builder and executes Selenium tools.
    Compatible with both OpenAI Agent Builder and MCP validation.
    """
    try:
        data = await request.json()
    except Exception as e:
        return JSONResponse({"error": f"Invalid JSON: {str(e)}"}, status_code=400)

    tool = data.get("tool")
    args = (
        data.get("arguments")
        or data.get("args")
        or data.get("params")
        or {}
    )

    if not tool:
        return JSONResponse({"error": "Missing 'tool' argument."}, status_code=400)

    try:
        if tool == "selenium_open_page":
            url = args.get("url")
            if not url:
                return JSONResponse({"error": "Missing 'url' argument."}, status_code=400)
            result = selenium_open_page(url)
            return JSONResponse({"status": "success", "tool": tool, "result": result})

        elif tool == "selenium_click":
            url = args.get("url")
            selector = args.get("selector")
            if not url:
                return JSONResponse({"error": "Missing 'url' argument."}, status_code=400)
            if not selector:
                return JSONResponse({"error": "Missing 'selector' argument."}, status_code=400)

            result = selenium_click(url, selector)
            return JSONResponse({"status": "success", "tool": tool, "result": result})


        elif tool == "selenium_get_text":
            url = args.get("url")
            selector = args.get("selector")
            if not url:
                return JSONResponse({"error": "Missing 'url' argument."}, status_code=400)
            if not selector:
                return JSONResponse({"error": "Missing 'selector' argument."}, status_code=400)

            result = selenium_get_text(url, selector)
            return JSONResponse({"status": "success", "tool": tool, "result": result})

        elif tool == "selenium_screenshot":
            url = args.get("url")
            if not url:
                return JSONResponse({"error": "Missing 'url' argument."}, status_code=400)

            filename = args.get("filename", "screenshot.png")
            try:
                result = selenium_screenshot(url, filename)
                return JSONResponse({"status": "success", "tool": tool, "result": result})
            except Exception as e:
                return JSONResponse(
                {"status": "error", "tool": tool, "error": f"Screenshot failed: {str(e)}"},
                status_code=200,
            )

        else:
            return JSONResponse(
                {"status": "error", "error": f"Unknown tool '{tool}'."},
                status_code=404,
            )

    except Exception as e:
        # Catch-all safeguard: no unhandled exceptions → no 500s
        return JSONResponse(
            {"status": "error", "tool": tool, "error": f"Server exception: {str(e)}"},
            status_code=200,
        )


# ----------------------------------------------------------
# Tool Handler: selenium_open_page
# ----------------------------------------------------------
async def handle_open_page(args: dict):
    url = args.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url' argument.")

    chrome_opts = Options()
    chrome_opts.add_argument("--headless")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.binary_location = CHROME_BINARY

    try:
        with webdriver.Chrome(options=chrome_opts) as driver:
            driver.get(url)
            title = driver.title
        return {"url": url, "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Selenium error: {e}")

# ----------------------------------------------------------
# Diagnostic Route (Enhanced + Self-Disable Switch + Startup Log)
# ----------------------------------------------------------
from fastapi import FastAPI, HTTPException

@app.get("/envcheck")
def envcheck():
    # 🔒 0️⃣ Debug mode check — route only active when DEBUG_MODE=True
    debug_mode = os.getenv("DEBUG_MODE", "False").lower() in ("true", "1", "yes")
    if not debug_mode:
        raise HTTPException(
            status_code=403,
            detail="Diagnostic route disabled. Set DEBUG_MODE=True to enable."
        )

    render_env_path = "/etc/secrets/.env"
    local_env_path = ".env"

    # 1️⃣ Determine which .env file is loaded
    if os.path.exists(render_env_path):
        env_source = render_env_path
    elif os.path.exists(local_env_path):
        env_source = local_env_path
    else:
        env_source = "No .env file found (likely environment vars only)."

    # 2️⃣ Gather basic env info safely
    env_preview = {
        "ENV_SOURCE": env_source,
        "RENDER": os.getenv("RENDER", "False"),
        "PYTHON_VERSION": os.getenv("PYTHON_VERSION", "Not set"),
        "CHROME_BINARY": os.getenv("CHROME_BINARY", "Not set"),
        "OPENAI_API_KEY_PREFIX": os.getenv("OPENAI_API_KEY", "")[:5] + "..."
        if os.getenv("OPENAI_API_KEY")
        else "Not set",
    }

    # 3️⃣ Test OpenAI API connectivity
    openai_status = {}
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if openai.api_key:
            models = openai.models.list()
            openai_status = {
                "api_status": "ok",
                "models_found": len(models.data),
                "first_model": models.data[0].id if models.data else "none",
            }
        else:
            openai_status = {"api_status": "missing_key"}
    except Exception as e:
        openai_status = {"api_status": "error", "error": str(e)}

    return {
        "env_status": "ok",
        "details": env_preview,
        "openai_check": openai_status,
    }

def _run(cmd: str):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
        return {"cmd": cmd, "ok": True, "out": out.strip()}
    except subprocess.CalledProcessError as e:
        return {"cmd": cmd, "ok": False, "code": e.returncode, "out": (e.output or "").strip()}
    except Exception as e:
        return {"cmd": cmd, "ok": False, "error": str(e)}


@app.get("/diag/chrome")
def diag_chrome():
    debug_mode = os.getenv("DEBUG_MODE", "false").lower() in ("1", "true", "yes")
    on_render = os.getenv("RENDER", "false").lower() in ("1", "true", "yes")

    # Allow diagnostics on Render OR when DEBUG_MODE=true locally
    if not (debug_mode or on_render):
        raise HTTPException(status_code=403, detail="Disabled. Set DEBUG_MODE=true to enable.")

    return {
        "env": {
            "RENDER": os.getenv("RENDER"),
            "CHROME_BINARY": os.getenv("CHROME_BINARY"),
            "SELENIUM_MANAGER": os.getenv("SELENIUM_MANAGER"),
            "PATH": os.getenv("PATH"),
        },
        "which": {
            "chromium": _run("which chromium || which chromium-browser || true"),
            "google_chrome": _run("which google-chrome || which google-chrome-stable || true"),
            "chromedriver": _run("which chromedriver || true"),
        },
        "versions": {
            "chromium": _run("chromium --version || chromium-browser --version || true"),
            "chrome": _run("google-chrome --version || google-chrome-stable --version || true"),
            "chromedriver": _run("chromedriver --version || true"),
        },
        "ldd": {
            "chromedriver": _run("ldd $(which chromedriver) 2>/dev/null | grep 'not found' || echo OK"),
            "chrome_bin": _run(
                "BIN=$(which chromium || which chromium-browser || which google-chrome || which google-chrome-stable || true); "
                "if [ -n \"$BIN\" ]; then ldd \"$BIN\" 2>/dev/null | grep 'not found' || echo OK; else echo 'NO_BROWSER_BIN'; fi"
            ),
        },
        "cache": {
            "selenium_cache": _run("ls -la /root/.cache/selenium || true"),
            "selenium_drivers": _run("find /root/.cache/selenium -maxdepth 6 -type f -name chromedriver -ls || true"),
        },
    }


# ----------------------------------------------------------
# Local Run Entrypoint (for local testing only)
# ----------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    resolved_version = locals().get("resolved_version", "unknown")

    debug_mode = os.getenv("DEBUG_MODE", "False").lower() in ("true", "1", "yes")
    if debug_mode:
        print("[DEBUG] Diagnostic route enabled — use /envcheck for environment and API verification")

    print(f"[INFO] Launching MCP Server on port 10000 (version={resolved_version})")
    uvicorn.run(app, host="0.0.0.0", port=10000)

# ----------------------------------------------------------
# Local Run Entrypoint (for local testing only)
# ----------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print(f"[INFO] Launching MCP Server on port 10000 (version={resolved_version})")
    uvicorn.run(app, host="0.0.0.0", port=10000)

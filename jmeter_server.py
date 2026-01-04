# jmeter_server.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

# Your existing JMeter tool module
from tools import jmeter_tools

# -----------------------------------------------------------------------------
# App + config
# -----------------------------------------------------------------------------

APP_NAME = os.getenv("SERVER_NAME", "JMeter MCP")
APP_DESC = os.getenv(
    "SERVER_DESC",
    "JMeter execution + reporting tools exposed via MCP-compatible FastAPI endpoints.",
)
APP_VERSION = os.getenv("MCP_VERSION", os.getenv("VERSION", "dev"))

# Optional: protect report endpoints with a simple token:
# - If REPORT_TOKEN is set, report endpoints require ?token=... or header X-Report-Token: ...
REPORT_TOKEN = os.getenv("REPORT_TOKEN", "").strip()

# Optional: used for absolute URLs in meta tags
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

app = FastAPI(title=APP_NAME, description=APP_DESC, version=APP_VERSION)

# CORS: keep permissive for MCP tooling + dev. Tighten if you want.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _require_report_token(request: Request, token: Optional[str]) -> None:
    """If REPORT_TOKEN is configured, require it."""
    if not REPORT_TOKEN:
        return

    header_token = request.headers.get("x-report-token") or request.headers.get("X-Report-Token")
    effective = token or header_token
    if effective != REPORT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

def _get_run_paths_or_404(run_id: str) -> Dict[str, Path]:
    """
    Prefer jmeter_tools._run_paths if available; otherwise infer using /summary or existing fields.
    """
    # If you have internal helper exposed, use it
    if hasattr(jmeter_tools, "_run_paths"):
        paths = jmeter_tools._run_paths(run_id)  # type: ignore[attr-defined]
        # Normalize to Path
        return {k: Path(v) for k, v in paths.items()}

    # Fallback: use your summary (must exist)
    summary = jmeter_tools.get_run_summary(run_id)
    if not summary or not summary.get("ok"):
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")

    html_dir = Path(summary["html_dir"])
    jtl_path = Path(summary["jtl_path"])
    log_path = Path(summary["log_path"])
    meta_path = (html_dir.parent / "meta.json")
    return {
        "html_dir": html_dir,
        "jtl_path": jtl_path,
        "log_path": log_path,
        "meta_path": meta_path,
    }

def _safe_join(base: Path, rel: str) -> Path:
    """
    Prevent directory traversal: resolve and ensure the result stays within base.
    """
    # Normalize slashes and remove leading slash
    rel = rel.lstrip("/").replace("\\", "/")

    # Disallow obvious traversal
    if ".." in rel.split("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    target = (base / rel).resolve()
    base_resolved = base.resolve()

    if not str(target).startswith(str(base_resolved)):
        raise HTTPException(status_code=400, detail="Invalid path")

    return target

def _guess_content_type(p: Path) -> str:
    s = p.suffix.lower()
    if s == ".html":
        return "text/html; charset=utf-8"
    if s == ".css":
        return "text/css; charset=utf-8"
    if s == ".js":
        return "application/javascript; charset=utf-8"
    if s == ".json":
        return "application/json; charset=utf-8"
    if s == ".svg":
        return "image/svg+xml"
    if s == ".png":
        return "image/png"
    if s == ".jpg" or s == ".jpeg":
        return "image/jpeg"
    if s == ".gif":
        return "image/gif"
    if s == ".woff":
        return "font/woff"
    if s == ".woff2":
        return "font/woff2"
    return "application/octet-stream"

def _inject_social_meta(html: str, *, title: str, description: str, url: str) -> str:
    """
    Inject OpenGraph/Twitter tags for nice LinkedIn previews.
    Uses a simple </head> insertion.
    """
    meta = f"""
<meta property="og:type" content="website"/>
<meta property="og:title" content="{title}"/>
<meta property="og:description" content="{description}"/>
<meta property="og:url" content="{url}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{title}"/>
<meta name="twitter:description" content="{description}"/>
""".strip()

    # If you later add a static preview image, you can add:
    # <meta property="og:image" content="..."/>

    if "</head>" in html:
        return html.replace("</head>", meta + "\n</head>", 1)
    # fallback
    return meta + "\n" + html

def _build_public_url(request: Request, path: str) -> str:
    """
    Prefer PUBLIC_BASE_URL if set; otherwise derive from request.
    """
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return f"{base}{path}"

# -----------------------------------------------------------------------------
# Root / health
# -----------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "ok": True,
        "service": "jmeter_mcp",
        "version": APP_VERSION,
        "schema": "/mcp/schema",
    }

# -----------------------------------------------------------------------------
# MCP schema endpoint
# -----------------------------------------------------------------------------

@app.get("/mcp/schema")
def serve_schema(request: Request):
    """
    Minimal MCP-style schema response (mirrors what you’re doing in mcp_server.py).
    """
    base = str(request.base_url).rstrip("/") + "/"
    return {
        "type": "mcp_server",
        "version": APP_VERSION,
        "mcp_version": APP_VERSION,
        "server_info": {
            "name": APP_NAME,
            "description": APP_DESC,
            "version": APP_VERSION,
            "runtime": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
        },
        "capabilities": {
            "invocation": "True",
            "streaming": "False",
            "multi_tool": "False",
        },
        # Tools list is optional here; you can enrich this later if you want.
        "endpoints": {
            "schema": f"{base}mcp/schema",
            "ping": f"{base}jmeter/ping",
        },
    }

# -----------------------------------------------------------------------------
# JMETER API routes
# -----------------------------------------------------------------------------

@app.get("/jmeter/ping")
def jmeter_ping():
    return jmeter_tools.ping()

@app.get("/jmeter/plans")
def jmeter_plans():
    return jmeter_tools.list_plans()

@app.get("/jmeter/version")
def jmeter_version(raw: bool = Query(False)):
    data = jmeter_tools.jmeter_version()
    if not raw:
        data.pop("raw", None)
    return data

@app.post("/jmeter/run")
def jmeter_run(payload: dict = Body(...)):
    plan = payload.get("plan")
    run_id = payload.get("run_id")
    extra_args = payload.get("extra_args")
    return jmeter_tools.run_test(plan=plan, run_id=run_id, extra_args=extra_args)

@app.get("/jmeter/run/{run_id}")
def jmeter_run_status(run_id: str):
    # Your tools file must implement run_status; you already fixed this locally.
    return jmeter_tools.run_status(run_id)

@app.get("/jmeter/run/{run_id}/summary")
def jmeter_run_summary(run_id: str):
    return jmeter_tools.get_run_summary(run_id)

@app.get("/jmeter/run/{run_id}/jtl/header")
def jmeter_run_jtl_header(run_id: str):
    return jmeter_tools.get_jtl_header(run_id)

# -----------------------------------------------------------------------------
# Report exposure (safe + preview-friendly)
# -----------------------------------------------------------------------------

@app.get("/jmeter/run/{run_id}/report/")
def jmeter_report_index(
    request: Request,
    run_id: str,
    token: Optional[str] = Query(default=None),
):
    """
    Pretty landing route for the JMeter dashboard with injected social meta tags.
    """
    _require_report_token(request, token)

    paths = _get_run_paths_or_404(run_id)
    html_dir = paths["html_dir"]
    index_path = (html_dir / "index.html")

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    raw_html = index_path.read_text(encoding="utf-8", errors="replace")

    # Build a stable public URL for meta
    page_url = _build_public_url(request, f"/jmeter/run/{run_id}/report/")

    # Basic branding/metadata
    title = f"JMeter Dashboard — Run {run_id}"
    desc = f"Performance dashboard generated by JMeter MCP for run {run_id}."

    # IMPORTANT: Make relative asset URLs resolve from /report/raw/
    # JMeter dashboard typically references ./content/... etc.
    # We'll rewrite base href to point to the raw folder.
    # If a <base> already exists, we replace it; otherwise we inject it.
    base_href = f"/jmeter/run/{run_id}/report/raw/"
    if "<base" in raw_html:
        raw_html = re.sub(r"<base[^>]*>", f'<base href="{base_href}">', raw_html, count=1, flags=re.IGNORECASE)
    else:
        raw_html = raw_html.replace("<head>", f'<head>\n<base href="{base_href}">', 1)

    enriched = _inject_social_meta(raw_html, title=title, description=desc, url=page_url)

    return HTMLResponse(content=enriched, status_code=200)

@app.get("/jmeter/run/{run_id}/report/raw/{file_path:path}")
def jmeter_report_raw(
    request: Request,
    run_id: str,
    file_path: str,
    token: Optional[str] = Query(default=None),
):
    """
    Serve raw dashboard assets safely from the run's html_dir.
    """
    _require_report_token(request, token)

    paths = _get_run_paths_or_404(run_id)
    html_dir = paths["html_dir"]
    if not html_dir.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    # Default file when someone hits /raw/ directly
    if not file_path or file_path.endswith("/"):
        file_path = file_path + "index.html" if file_path else "index.html"

    target = _safe_join(html_dir, file_path)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    content_type = _guess_content_type(target)
    data = target.read_bytes()

    # Avoid caching dashboards by default
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    }
    return Response(content=data, media_type=content_type, headers=headers)
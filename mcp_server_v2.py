"""Selenium MCP Server (Streamable HTTP) for ChatGPT Apps / Connectors.

This server uses the official MCP Python SDK (FastMCP) and exposes a small
browser-automation toolset over the MCP Streamable HTTP transport.

Endpoint (default): http://<host>:<port>/mcp

Design goals:
  - MCP-native (no custom FastAPI routes required)
  - Session-based browser control (so multi-step workflows actually work)
  - Container-friendly headless Chrome defaults
  - Conservative safety: explicit session lifecycle + timeouts
"""

from __future__ import annotations

import base64
import os
import threading
import time
import uuid
import contextlib
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse
from starlette.responses import RedirectResponse
from dataclasses import dataclass
from typing import Dict, Optional

from mcp.server.fastmcp import FastMCP

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# MCP server instance
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "selenium-mcp-appstore.onrender.com")

mcp = FastMCP(
    "SeleniumMCP",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "localhost:*",
            "127.0.0.1:*",
            f"{PUBLIC_HOST}:*",
            PUBLIC_HOST,  # safe extra
        ],
        allowed_origins=[
            f"https://{PUBLIC_HOST}",
            f"https://{PUBLIC_HOST}:*",
            # optional (useful when ChatGPT is the caller):
            "https://chat.openai.com",
            "https://chatgpt.com",
        ],
    ),
)


@dataclass
class _Session:
    driver: webdriver.Chrome
    created_at: float
    last_used_at: float


class _SessionManager:
    """In-process session registry.

    For hosted deployments, *do not* run multiple replicas without sticky
    sessions, because browser sessions are in-memory.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, _Session] = {}

    def _new_driver(self) -> webdriver.Chrome:
        opts = ChromeOptions()

        # Use env overrides when needed (e.g., custom Chrome path in Docker).
        chrome_binary = os.getenv("CHROME_BINARY")
        if chrome_binary:
            opts.binary_location = chrome_binary

        # Headless defaults suitable for containers.
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1365,768")

        # Reduce automation banners.
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        driver_path = os.getenv("CHROMEDRIVER_PATH")
        if driver_path:
            service = ChromeService(executable_path=driver_path)
            return webdriver.Chrome(service=service, options=opts)

        return webdriver.Chrome(options=opts)

    def create(self) -> str:
        with self._lock:
            sid = str(uuid.uuid4())
            now = time.time()
            self._sessions[sid] = _Session(
                driver=self._new_driver(),
                created_at=now,
                last_used_at=now,
            )
            return sid

    def get(self, session_id: str) -> _Session:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"Unknown session_id: {session_id}")
            s = self._sessions[session_id]
            s.last_used_at = time.time()
            return s

    def close(self, session_id: str) -> bool:
        with self._lock:
            s = self._sessions.pop(session_id, None)
        if not s:
            return False
        try:
            s.driver.quit()
        finally:
            return True

    def reap_idle(self, max_idle_seconds: int) -> int:
        """Close sessions idle longer than `max_idle_seconds`. Returns count."""
        now = time.time()
        to_close: list[str] = []
        with self._lock:
            for sid, s in self._sessions.items():
                if now - s.last_used_at > max_idle_seconds:
                    to_close.append(sid)
        closed = 0
        for sid in to_close:
            if self.close(sid):
                closed += 1
        return closed


SESSIONS = _SessionManager()


def _wait_css(driver: webdriver.Chrome, selector: str, timeout_s: int) -> None:
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )


@mcp.tool(
    name="create_session",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
def create_session() -> dict:
    """Create a new headless browser session and return its session_id."""
    session_id = SESSIONS.create()
    return {"session_id": session_id}


@mcp.tool(
    name="close_session",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    },
)
def close_session(session_id: str) -> dict:
    """Close a previously created browser session (frees resources)."""
    return {"closed": SESSIONS.close(session_id)}


@mcp.tool(
    name="open_page",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
def open_page(session_id: str, url: str, wait_css: Optional[str] = None, timeout_s: int = 20) -> dict:
    """Navigate the session to a URL.

    Args:
      session_id: Browser session id from create_session
      url: URL to navigate to
      wait_css: Optional CSS selector to wait for before returning
      timeout_s: Wait timeout (seconds)
    """
    s = SESSIONS.get(session_id)
    s.driver.get(url)
    if wait_css:
        _wait_css(s.driver, wait_css, timeout_s)
    return {"ok": True, "url": url, "title": s.driver.title}


@mcp.tool(
    name="click",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
def click(session_id: str, css_selector: str, timeout_s: int = 20) -> dict:
    """Click the first element matching a CSS selector."""
    s = SESSIONS.get(session_id)
    _wait_css(s.driver, css_selector, timeout_s)
    el = s.driver.find_element(By.CSS_SELECTOR, css_selector)
    el.click()
    return {"ok": True, "clicked": css_selector}


@mcp.tool(
    name="type_text",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
def type_text(
    session_id: str,
    css_selector: str,
    text: str,
    clear_first: bool = True,
    timeout_s: int = 20,
) -> dict:
    """Type text into an input/textarea located by CSS selector."""
    s = SESSIONS.get(session_id)
    _wait_css(s.driver, css_selector, timeout_s)
    el = s.driver.find_element(By.CSS_SELECTOR, css_selector)
    if clear_first:
        el.clear()
    el.send_keys(text)
    return {"ok": True, "selector": css_selector, "chars": len(text)}


@mcp.tool(
    name="get_text",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
def get_text(session_id: str, css_selector: str, timeout_s: int = 20) -> dict:
    """Return the `.text` content of the first element matching the selector."""
    s = SESSIONS.get(session_id)
    _wait_css(s.driver, css_selector, timeout_s)
    el = s.driver.find_element(By.CSS_SELECTOR, css_selector)
    return {"ok": True, "selector": css_selector, "text": el.text}


@mcp.tool(
    name="screenshot",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
def screenshot(session_id: str) -> dict:
    """Take a PNG screenshot and return it as base64."""
    s = SESSIONS.get(session_id)
    b64 = s.driver.get_screenshot_as_base64()
    # Keep response small-ish; caller can store it as a file if needed.
    return {
        "ok": True,
        "mime_type": "image/png",
        "image_base64": b64,
    }


@mcp.tool(
    name="reap_idle_sessions",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    },
)
def reap_idle_sessions(max_idle_seconds: int = 600) -> dict:
    """Close sessions idle for longer than max_idle_seconds."""
    return {"closed": SESSIONS.reap_idle(max_idle_seconds)}


if __name__ == "__main__":
    # By convention, MCP over Streamable HTTP is served at /mcp.
    # For ChatGPT connectors, you’ll register: https://<your-domain>/mcp
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

async def health(request):
    return JSONResponse({"status": "ok"})

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/mcp/", lambda request: RedirectResponse(url="/mcp", status_code=307)),
        Mount("/", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
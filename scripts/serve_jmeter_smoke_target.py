#!/usr/bin/env python3
"""Serve the deterministic HTTP target used by the MCP-to-JMeter smoke test."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class SmokeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/get":
            self.send_error(404)
            return
        body = b'{"ok":true,"source":"jmeter-mcp-smoke"}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    port = int(os.getenv("JMETER_SMOKE_TARGET_PORT", "18080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), SmokeHandler)
    print(json.dumps({"status": "ready", "port": port}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

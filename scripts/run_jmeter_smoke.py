#!/usr/bin/env python3
"""Run a deterministic end-to-end smoke test through the real JMeter binary."""

from __future__ import annotations

import csv
import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jmeter_executor import ExecutorConfig, JMeterExecutor  # noqa: E402


RUN_ID = uuid.uuid4().hex[:12]


class SmokeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/get":
            self.send_error(404)
            return
        body = b'{"ok":true,"source":"jmeter-docker-smoke"}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def _assert_jtl(jtl_path: Path) -> dict[str, Any]:
    with jtl_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 1:
        raise AssertionError(f"Expected exactly one JMeter sample; found {len(rows)}")

    sample = rows[0]
    if sample.get("success", "").lower() != "true":
        raise AssertionError(f"JMeter sample failed: {sample}")
    if sample.get("responseCode") != "200":
        raise AssertionError(f"Expected HTTP 200; found {sample.get('responseCode')!r}")
    if sample.get("label") != "GET smoke target /get":
        raise AssertionError(f"Unexpected JMeter sample label: {sample.get('label')!r}")

    return {
        "samples": len(rows),
        "response_code": sample["responseCode"],
        "elapsed_ms": int(sample["elapsed"]),
        "latency_ms": int(sample["Latency"]),
        "connect_ms": int(sample["Connect"]),
    }


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        executor = JMeterExecutor(
            ExecutorConfig.for_project(
                PROJECT_ROOT,
                timeout_seconds=120,
                allowed_properties=(
                    "smoke_host",
                    "smoke_path",
                    "smoke_port",
                    "smoke_protocol",
                ),
            )
        )
        version = executor.version()
        if not version["ok"] or version.get("version") != "5.6.3":
            raise AssertionError(f"Unexpected JMeter version result: {version}")
        result = executor.run(
            plan="httpbin_smoke.jmx",
            run_id=RUN_ID,
            properties={
                "smoke_host": "127.0.0.1",
                "smoke_port": server.server_port,
                "smoke_protocol": "http",
                "smoke_path": "/get",
            },
        )

        if not result["ok"]:
            raise AssertionError(f"JMeter execution failed: {result}")

        jtl_path = Path(result["jtl_path"])
        dashboard = Path(result["html_dir"]) / "index.html"
        log_path = Path(result["log_path"])
        if not jtl_path.is_file():
            raise AssertionError("JMeter did not produce results.jtl")
        if not log_path.is_file():
            raise AssertionError("JMeter did not produce jmeter.log")
        if not dashboard.is_file():
            raise AssertionError("JMeter did not produce the HTML dashboard")

        evidence = {
            "ok": True,
            "jmeter_version": version.get("version"),
            "run_id": RUN_ID,
            "status": result["status"],
            "dashboard": str(dashboard.relative_to(PROJECT_ROOT)),
            "jtl": str(jtl_path.relative_to(PROJECT_ROOT)),
            **_assert_jtl(jtl_path),
        }
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())

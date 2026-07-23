#!/usr/bin/env python3
"""Run a deterministic end-to-end smoke test through the real JMeter binary."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
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


def _invoke_cli(arguments: list[str], environment: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "jmeter_executor", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "JMeter CLI failed "
            f"(exit={completed.returncode}, stdout={completed.stdout!r}, "
            f"stderr={completed.stderr!r})"
        )
    if completed.stderr:
        raise AssertionError(f"JMeter CLI wrote unexpected stderr: {completed.stderr!r}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"JMeter CLI returned invalid JSON: {completed.stdout!r}") from exc
    if not payload.get("ok"):
        raise AssertionError(f"JMeter CLI returned an error envelope: {payload}")
    return payload


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        environment = dict(os.environ)
        environment.update(
            {
                "JMETER_PROJECT_ROOT": str(PROJECT_ROOT),
                "JMETER_TIMEOUT_SECONDS": "120",
                "JMETER_ALLOWED_PROPERTIES": ",".join(
                    ("smoke_host", "smoke_path", "smoke_port", "smoke_protocol")
                ),
                "PYTHONPATH": str(PROJECT_ROOT),
            }
        )
        version = _invoke_cli(["version"], environment)["result"]
        if not version["ok"] or version.get("version") != "5.6.3":
            raise AssertionError(f"Unexpected JMeter version result: {version}")
        result = _invoke_cli(
            [
                "run",
                "--plan",
                "httpbin_smoke.jmx",
                "--run-id",
                RUN_ID,
                "--property",
                "smoke_host=127.0.0.1",
                "--property",
                f"smoke_port={server.server_port}",
                "--property",
                "smoke_protocol=http",
                "--property",
                "smoke_path=/get",
            ],
            environment,
        )["result"]

        if not result["ok"]:
            raise AssertionError(f"JMeter execution failed: {result}")
        status = _invoke_cli(["status", "--run-id", RUN_ID], environment)["result"]
        if status["status"] != "completed":
            raise AssertionError(f"Unexpected CLI status result: {status}")
        manifest = _invoke_cli(
            ["artifact-manifest", "--run-id", RUN_ID], environment
        )["result"]
        metrics = _invoke_cli(
            ["metrics-summary", "--run-id", RUN_ID], environment
        )["result"]
        if manifest.get("schema_version") != "pe.jmeter.evidence.v1":
            raise AssertionError(f"Unexpected evidence manifest: {manifest}")
        expected_artifacts = {
            "test_plan", "jtl", "jmeter_log", "dashboard_index", "run_metadata"
        }
        if set(manifest.get("artifacts", {})) != expected_artifacts:
            raise AssertionError(f"Incomplete evidence manifest: {manifest}")
        for name, artifact in manifest["artifacts"].items():
            digest = artifact.get("sha256")
            if not artifact.get("exists") or not isinstance(digest, str) or len(digest) != 64:
                raise AssertionError(f"Invalid evidence for {name}: {artifact}")
        if metrics.get("schema_version") != "pe.jmeter.metrics.v1":
            raise AssertionError(f"Unexpected metrics summary: {metrics}")
        if metrics["summary"]["sample_count"] != 1:
            raise AssertionError(f"Unexpected sample count: {metrics}")
        if metrics["summary"]["error_count"] != 0:
            raise AssertionError(f"Unexpected JMeter errors: {metrics}")
        if metrics["source_jtl"]["sha256"] != manifest["artifacts"]["jtl"]["sha256"]:
            raise AssertionError("Metrics source JTL does not match evidence manifest")

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
            "evidence_schema": manifest["schema_version"],
            "metrics_schema": metrics["schema_version"],
            "metrics": metrics["summary"],
            "artifact_sha256": {
                name: artifact["sha256"]
                for name, artifact in manifest["artifacts"].items()
            },
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

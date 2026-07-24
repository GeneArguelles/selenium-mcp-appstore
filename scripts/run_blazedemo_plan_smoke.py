#!/usr/bin/env python3
"""Validate the BlazeDemo journey plan through real JMeter and a local fixture."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = uuid.uuid4().hex[:12]
EXPECTED_LABELS = {
    "01 Home page": 6,
    "02 Search Boston to London": 6,
    "03 Select demonstration flight": 6,
    "04 Confirm synthetic purchase": 6,
}


class BlazeDemoFixtureServer(ThreadingHTTPServer):
    request_counts: Counter[str]

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, BlazeDemoFixtureHandler)
        self.request_counts = Counter()
        self.request_counts_lock = threading.Lock()

    def record(self, method: str, path: str) -> None:
        with self.request_counts_lock:
            self.request_counts[f"{method} {path}"] += 1


class BlazeDemoFixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def fixture_server(self) -> BlazeDemoFixtureServer:
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.fixture_server.record("GET", self.path)
        if self.path != "/":
            self.send_error(404)
            return
        self._respond(
            200,
            "<html><h1>Welcome to the Simple Travel Agency!</h1></html>",
        )

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.fixture_server.record("POST", self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        fields = parse_qs(body, keep_blank_values=True)

        if self.path == "/reserve.php":
            if fields.get("fromPort") != ["Boston"] or fields.get("toPort") != [
                "London"
            ]:
                self._respond(400, "invalid route")
                return
            self._respond(200, "<html><h3>Flights from Boston to London</h3></html>")
            return

        if self.path == "/purchase.php":
            required = {
                "fromPort": "Boston",
                "toPort": "London",
                "airline": "Virgin America",
                "flight": "43",
                "price": "472.56",
            }
            if any(fields.get(name) != [value] for name, value in required.items()):
                self._respond(400, "invalid flight")
                return
            self._respond(
                200,
                "<html><p>Please submit the form below to purchase the flight.</p></html>",
            )
            return

        if self.path == "/confirmation.php":
            required = {
                "inputName": "PE Smoke Tester",
                "address": "100 Test Avenue",
                "city": "Testville",
                "state": "VA",
                "zipCode": "00000",
                "cardType": "visa",
                "creditCardNumber": "4111111111111111",
                "creditCardMonth": "11",
                "creditCardYear": "2030",
                "nameOnCard": "PE Smoke Tester",
            }
            if any(fields.get(name) != [value] for name, value in required.items()):
                self._respond(400, "invalid synthetic purchase")
                return
            self._respond(
                200,
                "<html><h1>Thank you for your purchase today!</h1></html>",
            )
            return

        self.send_error(404)

    def _respond(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


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


def _assert_jtl(jtl_path: Path) -> dict[str, Any]:
    with jtl_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 24:
        raise AssertionError(f"Expected 24 JMeter samples; found {len(rows)}")
    failures = [row for row in rows if row.get("success", "").lower() != "true"]
    if failures:
        raise AssertionError(f"JMeter assertions failed: {failures[:3]}")
    response_codes = Counter(row.get("responseCode") for row in rows)
    if response_codes != Counter({"200": 24}):
        raise AssertionError(f"Unexpected response codes: {response_codes}")
    labels = Counter(row.get("label") for row in rows)
    if labels != Counter(EXPECTED_LABELS):
        raise AssertionError(f"Unexpected sample labels: {labels}")
    return {
        "samples": len(rows),
        "labels": dict(sorted(labels.items())),
        "response_codes": dict(sorted(response_codes.items())),
    }


def main() -> int:
    server = BlazeDemoFixtureServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        environment = dict(os.environ)
        environment.update(
            {
                "JMETER_PROJECT_ROOT": str(PROJECT_ROOT),
                "JMETER_TIMEOUT_SECONDS": "120",
                "JMETER_ALLOWED_PROPERTIES": ",".join(
                    ("smoke_host", "smoke_port", "smoke_protocol")
                ),
                "PYTHONPATH": str(PROJECT_ROOT),
            }
        )
        result = _invoke_cli(
            [
                "run",
                "--plan",
                "blazedemo_booking_smoke.jmx",
                "--run-id",
                RUN_ID,
                "--property",
                "smoke_host=127.0.0.1",
                "--property",
                f"smoke_port={server.server_port}",
                "--property",
                "smoke_protocol=http",
            ],
            environment,
        )["result"]
        if result.get("status") != "completed":
            raise AssertionError(f"Unexpected JMeter result: {result}")

        manifest = _invoke_cli(
            ["artifact-manifest", "--run-id", RUN_ID], environment
        )["result"]
        metrics = _invoke_cli(
            ["metrics-summary", "--run-id", RUN_ID], environment
        )["result"]
        if metrics["summary"]["sample_count"] != 24:
            raise AssertionError(f"Unexpected metrics sample count: {metrics}")
        if metrics["summary"]["error_count"] != 0:
            raise AssertionError(f"Unexpected JMeter errors: {metrics}")
        if metrics["summary"]["samples_by_label"] != EXPECTED_LABELS:
            raise AssertionError(f"Unexpected metrics label counts: {metrics}")
        if metrics["source_jtl"]["sha256"] != manifest["artifacts"]["jtl"]["sha256"]:
            raise AssertionError("Metrics source JTL does not match evidence manifest")

        expected_requests = Counter(
            {
                "GET /": 6,
                "POST /reserve.php": 6,
                "POST /purchase.php": 6,
                "POST /confirmation.php": 6,
            }
        )
        if server.request_counts != expected_requests:
            raise AssertionError(f"Unexpected fixture traffic: {server.request_counts}")

        jtl_path = Path(result["jtl_path"])
        evidence = {
            "ok": True,
            "run_id": RUN_ID,
            "status": result["status"],
            "plan": "blazedemo_booking_smoke.jmx",
            "traffic_profile": {
                "threads": 3,
                "loops": 2,
                "journey_requests": 4,
                "expected_samples": 24,
            },
            "metrics_schema": metrics["schema_version"],
            "evidence_schema": manifest["schema_version"],
            "metrics": metrics["summary"],
            "fixture_requests": dict(sorted(server.request_counts.items())),
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

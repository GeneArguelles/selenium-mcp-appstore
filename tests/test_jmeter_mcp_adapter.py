from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jmeter_executor.mcp_adapter import JMeterMcpAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FAKE_JMETER = r"""#!/usr/bin/env python3
import pathlib
import sys

if "-v" in sys.argv:
    print(r"/_/   \_\_| /_/   \_\____|_| |_|_____|  \___/ 5.6.3")
    raise SystemExit(0)

args = sys.argv[1:]
properties = {}
for arg in args:
    if arg.startswith("-J") and "=" in arg:
        name, value = arg[2:].split("=", 1)
        properties[name] = value

jtl = pathlib.Path(args[args.index("-l") + 1])
log = pathlib.Path(args[args.index("-j") + 1])
html = pathlib.Path(args[args.index("-o") + 1])
jtl.write_text(
    "timeStamp,elapsed,label,responseCode,success,Latency,Connect\n"
    "1,12,mcp-smoke,200,true,8,3\n",
    encoding="utf-8",
)
log.write_text("fake jmeter log\n", encoding="utf-8")
html.mkdir()
(html / "index.html").write_text("<html>ok</html>", encoding="utf-8")
print("properties=" + repr(properties))
print("forbidden_secret_present=" + str("FORBIDDEN_SECRET" in __import__("os").environ))
"""


class JMeterMcpAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "testplans").mkdir()
        (self.root / "reports" / "runs").mkdir(parents=True)
        (self.root / "testplans" / "smoke.jmx").write_text(
            "<jmeterTestPlan/>", encoding="utf-8"
        )
        self.binary = self.root / "fake-jmeter"
        self.binary.write_text(FAKE_JMETER, encoding="utf-8")
        self.binary.chmod(0o755)

        self.environment = dict(os.environ)
        self.environment.update(
            {
                "FORBIDDEN_SECRET": "must-not-reach-cli-or-worker",
                "JMETER_BIN": str(self.binary),
                "JMETER_TIMEOUT_SECONDS": "2",
                "JMETER_ALLOWED_PROPERTIES": "threads",
            }
        )
        self.adapter = JMeterMcpAdapter(
            project_root=self.root,
            working_directory=PROJECT_ROOT,
            cli_timeout_seconds=5,
            environment=self.environment,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_discovery_methods_wrap_the_cli_contract(self) -> None:
        ping = self.adapter.ping()
        version = self.adapter.version()
        plans = self.adapter.list_plans()

        self.assertEqual(ping["schema_version"], "pe.jmeter.mcp.v1")
        self.assertEqual(ping["executor"]["schema_version"], "pe.jmeter.cli.v1")
        self.assertEqual(ping["tool"], "jmeter_ping")
        self.assertTrue(ping["result"]["jmeter_available"])
        self.assertEqual(version["result"]["version"], "5.6.3")
        self.assertEqual(plans["result"]["plans"], ["smoke.jmx"])

    def test_run_and_artifact_queries_cross_the_cli_boundary(self) -> None:
        run = self.adapter.run(
            plan="smoke.jmx",
            run_id="abcdef12",
            properties={"threads": "sensitive-value"},
        )
        status = self.adapter.status(run_id="abcdef12")
        details = self.adapter.run_details(run_id="abcdef12")
        header = self.adapter.jtl_header(run_id="abcdef12")
        manifest = self.adapter.artifact_manifest(run_id="abcdef12")

        self.assertTrue(run["ok"])
        self.assertEqual(run["result"]["status"], "completed")
        self.assertEqual(status["result"]["status"], "completed")
        self.assertNotIn("sensitive-value", repr(details))
        self.assertIn("<redacted>", details["result"]["stdout"])
        self.assertIn("forbidden_secret_present=False", details["result"]["stdout"])
        self.assertIn("elapsed", header["result"]["columns"])
        self.assertEqual(
            manifest["result"]["schema_version"], "pe.jmeter.evidence.v1"
        )
        self.assertRegex(
            manifest["result"]["artifacts"]["run_metadata"]["sha256"],
            r"^[a-f0-9]{64}$",
        )

    def test_cli_policy_errors_remain_machine_readable(self) -> None:
        rejected = self.adapter.run(
            plan="smoke.jmx",
            properties={"target_url": "https://unapproved.example"},
        )
        missing = self.adapter.status(run_id="deadbeef")

        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["executor"]["exit_code"], 2)
        self.assertEqual(rejected["error"]["type"], "ValidationError")
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["executor"]["exit_code"], 3)
        self.assertEqual(missing["error"]["type"], "RunNotFoundError")

    def test_adapter_rejects_non_string_property_values(self) -> None:
        response = self.adapter.run(  # type: ignore[arg-type]
            plan="smoke.jmx", properties={"threads": 2}
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "AdapterValidationError")
        self.assertIsNone(response["executor"]["exit_code"])

    def test_malformed_cli_output_is_not_forwarded_as_executor_data(self) -> None:
        malformed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"schema_version":"wrong"}\n', stderr=""
        )
        with patch("jmeter_executor.mcp_adapter.subprocess.run", return_value=malformed):
            response = self.adapter.ping()

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "AdapterProtocolError")
        self.assertEqual(response["executor"]["exit_code"], 0)

    def test_run_lock_rejects_concurrent_work_without_queueing(self) -> None:
        self.adapter._run_lock.acquire()
        try:
            response = self.adapter.run(plan="smoke.jmx")
        finally:
            self.adapter._run_lock.release()

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "RunBusyError")


if __name__ == "__main__":
    unittest.main()

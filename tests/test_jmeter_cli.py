from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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

if properties.get("fail") == "true":
    print("intentional failure")
    raise SystemExit(7)

jtl = pathlib.Path(args[args.index("-l") + 1])
log = pathlib.Path(args[args.index("-j") + 1])
html = pathlib.Path(args[args.index("-o") + 1])
jtl.write_text(
    "timeStamp,elapsed,label,responseCode,success,Latency,Connect\n"
    "1,12,cli-smoke,200,true,8,3\n",
    encoding="utf-8",
)
log.write_text("fake jmeter log\n", encoding="utf-8")
html.mkdir()
(html / "index.html").write_text("<html>ok</html>", encoding="utf-8")
print("properties=" + repr(properties))
"""


class JMeterCliTests(unittest.TestCase):
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
                "JMETER_PROJECT_ROOT": str(self.root),
                "JMETER_BIN": str(self.binary),
                "JMETER_TIMEOUT_SECONDS": "2",
                "JMETER_ALLOWED_PROPERTIES": "threads,fail",
                "PYTHONPATH": str(PROJECT_ROOT),
            }
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        completed = subprocess.run(
            [sys.executable, "-m", "jmeter_executor", *arguments],
            cwd=PROJECT_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.stderr, "")
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 1, completed.stdout)
        return completed, json.loads(lines[0])

    def test_discovery_commands_emit_versioned_json(self) -> None:
        ping, ping_payload = self.invoke("ping")
        plans, plans_payload = self.invoke("list-plans")
        version, version_payload = self.invoke("version")

        self.assertEqual(ping.returncode, 0)
        self.assertEqual(ping_payload["schema_version"], "pe.jmeter.cli.v1")
        self.assertTrue(ping_payload["result"]["jmeter_available"])
        self.assertEqual(plans.returncode, 0)
        self.assertEqual(plans_payload["result"]["plans"], ["smoke.jmx"])
        self.assertEqual(version.returncode, 0)
        self.assertEqual(version_payload["result"]["version"], "5.6.3")

    def test_run_status_details_and_jtl_header_round_trip(self) -> None:
        run, run_payload = self.invoke(
            "run",
            "--plan",
            "smoke.jmx",
            "--run-id",
            "abcdef12",
            "--property",
            "threads=sensitive-value",
        )
        status, status_payload = self.invoke("status", "--run-id", "abcdef12")
        details, details_payload = self.invoke("run-details", "--run-id", "abcdef12")
        header, header_payload = self.invoke("jtl-header", "--run-id", "abcdef12")
        manifest, manifest_payload = self.invoke(
            "artifact-manifest", "--run-id", "abcdef12"
        )

        self.assertEqual(run.returncode, 0)
        self.assertTrue(run_payload["ok"])
        self.assertEqual(run_payload["result"]["status"], "completed")
        self.assertEqual(status.returncode, 0)
        self.assertEqual(status_payload["result"]["status"], "completed")
        self.assertEqual(details.returncode, 0)
        self.assertNotIn("sensitive-value", details.stdout)
        self.assertIn("<redacted>", details_payload["result"]["stdout"])
        self.assertEqual(header.returncode, 0)
        self.assertIn("elapsed", header_payload["result"]["columns"])
        self.assertEqual(manifest.returncode, 0)
        self.assertEqual(
            manifest_payload["result"]["schema_version"], "pe.jmeter.evidence.v1"
        )
        self.assertRegex(
            manifest_payload["result"]["artifacts"]["jtl"]["sha256"],
            r"^[a-f0-9]{64}$",
        )

    def test_validation_not_found_conflict_and_run_failure_exit_codes(self) -> None:
        invalid, invalid_payload = self.invoke(
            "run", "--plan", "smoke.jmx", "--property", "target=unapproved"
        )
        missing, missing_payload = self.invoke("status", "--run-id", "deadbeef")

        first, _ = self.invoke("run", "--plan", "smoke.jmx", "--run-id", "c0ffee00")
        conflict, conflict_payload = self.invoke(
            "run", "--plan", "smoke.jmx", "--run-id", "c0ffee00"
        )
        failed, failed_payload = self.invoke(
            "run",
            "--plan",
            "smoke.jmx",
            "--run-id",
            "badc0de0",
            "--property",
            "fail=true",
        )

        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid_payload["error"]["type"], "ValidationError")
        self.assertEqual(missing.returncode, 3)
        self.assertEqual(missing_payload["error"]["type"], "RunNotFoundError")
        self.assertEqual(first.returncode, 0)
        self.assertEqual(conflict.returncode, 4)
        self.assertEqual(conflict_payload["error"]["type"], "RunConflictError")
        self.assertEqual(failed.returncode, 10)
        self.assertFalse(failed_payload["ok"])
        self.assertEqual(failed_payload["result"]["status"], "failed")

    def test_usage_errors_are_json_and_do_not_write_to_stderr(self) -> None:
        missing_command, payload = self.invoke()
        malformed, malformed_payload = self.invoke(
            "run", "--plan", "smoke.jmx", "--property", "not-an-assignment"
        )

        self.assertEqual(missing_command.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "CliUsageError")
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(malformed_payload["error"]["type"], "CliUsageError")


if __name__ == "__main__":
    unittest.main()

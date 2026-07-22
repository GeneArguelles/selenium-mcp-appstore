from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jmeter_executor import (
    ExecutorConfig,
    JMeterExecutor,
    RunConflictError,
    ValidationError,
)
from tools import jmeter_tools


FAKE_JMETER = r"""#!/usr/bin/env python3
import pathlib
import sys
import time

if "-v" in sys.argv:
    print("Apache JMeter (version 5.6.3)")
    raise SystemExit(0)

args = sys.argv[1:]
properties = {}
for arg in args:
    if arg.startswith("-J") and "=" in arg:
        name, value = arg[2:].split("=", 1)
        properties[name] = value

if "delay" in properties:
    time.sleep(float(properties["delay"]))

jtl = pathlib.Path(args[args.index("-l") + 1])
log = pathlib.Path(args[args.index("-j") + 1])
html = pathlib.Path(args[args.index("-o") + 1])
jtl.write_text(
    "timeStamp,elapsed,label,responseCode,success,Latency,Connect\n"
    "1,12,smoke,200,true,8,3\n",
    encoding="utf-8",
)
log.write_text("fake jmeter log\n", encoding="utf-8")
html.mkdir()
(html / "index.html").write_text("<html>ok</html>", encoding="utf-8")
print("properties=" + repr(properties))
print("forbidden_secret_present=" + str("FORBIDDEN_SECRET" in __import__("os").environ))
"""


class JMeterExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.testplans = self.root / "testplans"
        self.runs = self.root / "runs"
        self.testplans.mkdir()
        self.runs.mkdir()
        (self.testplans / "smoke.jmx").write_text("<jmeterTestPlan/>", encoding="utf-8")
        self.binary = self.root / "fake-jmeter"
        self.binary.write_text(FAKE_JMETER, encoding="utf-8")
        self.binary.chmod(0o755)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def executor(
        self,
        *,
        timeout: float = 2.0,
        allowed_properties: frozenset[str] = frozenset(),
    ) -> JMeterExecutor:
        return JMeterExecutor(
            ExecutorConfig(
                testplans_dir=self.testplans,
                runs_dir=self.runs,
                jmeter_bin=str(self.binary),
                timeout_seconds=timeout,
                terminate_grace_seconds=0.05,
                allowed_properties=allowed_properties,
            )
        )

    def test_version_and_plan_discovery(self) -> None:
        executor = self.executor()

        self.assertEqual(executor.list_plans(), {"ok": True, "plans": ["smoke.jmx"]})
        self.assertEqual(executor.version()["version"], "5.6.3")

    def test_plan_symlink_cannot_escape_approved_directory(self) -> None:
        outside = self.root / "outside.jmx"
        outside.write_text("<jmeterTestPlan/>", encoding="utf-8")
        try:
            os.symlink(outside, self.testplans / "escaped.jmx")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")

        executor = self.executor()

        self.assertEqual(executor.list_plans()["plans"], ["smoke.jmx"])
        with self.assertRaises(ValidationError):
            executor.run(plan="escaped.jmx")

    def test_run_id_is_confined_to_lowercase_hex(self) -> None:
        executor = self.executor()

        for invalid in ("../outside", "/tmp/outside", "ABCDEF12", "short", "abc/def12"):
            with self.subTest(run_id=invalid), self.assertRaises(ValidationError):
                executor.run_paths(invalid)

    def test_successful_run_creates_an_immutable_artifact_directory(self) -> None:
        executor = self.executor()
        result = executor.run(plan="smoke.jmx", run_id="abcdef12")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["jtl_exists"])
        self.assertTrue(result["log_exists"])
        self.assertTrue(result["html_exists"])
        self.assertEqual(
            executor.get_jtl_header("abcdef12")["columns"],
            ["timeStamp", "elapsed", "label", "responseCode", "success", "Latency", "Connect"],
        )

        marker = self.runs / "abcdef12" / "keep.txt"
        marker.write_text("do not delete", encoding="utf-8")
        with self.assertRaises(RunConflictError):
            executor.run(plan="smoke.jmx", run_id="abcdef12")
        self.assertEqual(marker.read_text(encoding="utf-8"), "do not delete")

    def test_only_allowlisted_properties_are_accepted_and_values_are_redacted(self) -> None:
        executor = self.executor(allowed_properties=frozenset({"threads"}))

        with self.assertRaises(ValidationError):
            executor.run(plan="smoke.jmx", properties={"target_url": "https://example.com"})

        executor.run(
            plan="smoke.jmx",
            run_id="1234abcd",
            properties={"threads": "super-sensitive-value"},
        )
        metadata_text = (self.runs / "1234abcd" / "run.json").read_text(encoding="utf-8")
        metadata = json.loads(metadata_text)

        self.assertNotIn("super-sensitive-value", metadata_text)
        self.assertIn("-Jthreads=<redacted>", metadata["command"])
        self.assertEqual(metadata["property_names"], ["threads"])

    def test_timeout_terminates_run_and_records_terminal_status(self) -> None:
        executor = self.executor(
            timeout=0.05,
            allowed_properties=frozenset({"delay"}),
        )

        result = executor.run(
            plan="smoke.jmx",
            run_id="deadbeef",
            properties={"delay": 5},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "timed_out")
        self.assertIn("exceeded timeout", result["error"])
        self.assertEqual(executor.get_run_summary("deadbeef")["status"], "timed_out")

    def test_worker_does_not_inherit_unapproved_parent_secrets(self) -> None:
        executor = self.executor()

        with patch.dict(os.environ, {"FORBIDDEN_SECRET": "must-not-reach-jmeter"}):
            executor.run(plan="smoke.jmx", run_id="feedface")

        metadata = json.loads(
            (self.runs / "feedface" / "run.json").read_text(encoding="utf-8")
        )
        self.assertIn("forbidden_secret_present=False", metadata["stdout"])
        self.assertNotIn("must-not-reach-jmeter", json.dumps(metadata))

    def test_legacy_adapter_rejects_raw_arguments_and_supplies_run_status(self) -> None:
        executor = self.executor()
        with patch.object(jmeter_tools, "_EXECUTOR", executor):
            rejected = jmeter_tools.run_test(
                "smoke.jmx",
                extra_args=["-Jtarget=https://unapproved.example"],
            )
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error_type"], "ValidationError")

            created = jmeter_tools.run_test("smoke.jmx", run_id="c0ffee00")
            status = jmeter_tools.run_status("c0ffee00")

        self.assertTrue(created["ok"])
        self.assertEqual(status["status"], "completed")


if __name__ == "__main__":
    unittest.main()

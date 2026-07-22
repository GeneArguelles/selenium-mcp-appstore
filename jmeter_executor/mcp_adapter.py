"""Persona Engineering MCP adapter for the machine-readable JMeter CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MCP_SCHEMA_VERSION = "pe.jmeter.mcp.v1"
CLI_SCHEMA_VERSION = "pe.jmeter.cli.v1"

_PASSTHROUGH_ENVIRONMENT = frozenset(
    {
        "HOME",
        "JAVA_HOME",
        "JMETER_ALLOWED_PROPERTIES",
        "JMETER_BIN",
        "JMETER_HOME",
        "JMETER_OPTS",
        "JMETER_TIMEOUT_SECONDS",
        "JRE_HOME",
        "JVM_ARGS",
        "LANG",
        "LC_ALL",
        "PATH",
        "TMPDIR",
        "TZ",
    }
)


class AdapterProtocolError(RuntimeError):
    """The CLI response did not satisfy the trusted adapter contract."""


@dataclass
class JMeterMcpAdapter:
    """Invoke the JMeter executor CLI without exposing arbitrary arguments.

    The adapter intentionally launches the CLI as a separate process. MCP callers
    can select only the fixed methods below; they cannot choose an executable,
    working directory, raw JMeter arguments, or environment variables.
    """

    project_root: Path
    working_directory: Path
    cli_timeout_seconds: float
    python_executable: str = sys.executable
    environment: Mapping[str, str] = field(
        default_factory=lambda: dict(os.environ), repr=False
    )
    _run_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root).resolve()
        self.working_directory = Path(self.working_directory).resolve()
        self.environment = dict(self.environment)
        if self.cli_timeout_seconds <= 0:
            raise ValueError("cli_timeout_seconds must be greater than zero")
        if not self.working_directory.is_dir():
            raise ValueError("working_directory must be an existing directory")

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "JMeterMcpAdapter":
        source = dict(os.environ if environment is None else environment)
        source_root = Path(__file__).resolve().parents[1]
        project_root = Path(source.get("JMETER_PROJECT_ROOT", str(source_root)))

        executor_timeout = _positive_float(
            source.get("JMETER_TIMEOUT_SECONDS", "600"),
            "JMETER_TIMEOUT_SECONDS",
        )
        adapter_timeout = _positive_float(
            source.get("JMETER_MCP_TIMEOUT_SECONDS", str(executor_timeout + 30)),
            "JMETER_MCP_TIMEOUT_SECONDS",
        )
        return cls(
            project_root=project_root,
            working_directory=source_root,
            cli_timeout_seconds=adapter_timeout,
            environment=source,
        )

    def ping(self) -> dict[str, Any]:
        return self._invoke("jmeter_ping", "ping")

    def version(self, *, include_raw: bool = False) -> dict[str, Any]:
        arguments = ["--include-raw"] if include_raw else []
        return self._invoke("jmeter_version", "version", arguments)

    def list_plans(self) -> dict[str, Any]:
        return self._invoke("jmeter_list_plans", "list-plans")

    def run(
        self,
        *,
        plan: str,
        run_id: str | None = None,
        properties: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._run_lock.acquire(blocking=False):
            return self._adapter_error(
                tool="jmeter_run",
                command="run",
                error_type="RunBusyError",
                message="Another JMeter run is active in this MCP server process",
            )

        try:
            arguments = ["--plan", plan]
            if run_id is not None:
                arguments.extend(("--run-id", run_id))
            property_items = list((properties or {}).items())
            for name, value in property_items:
                if not isinstance(name, str) or not isinstance(value, str):
                    return self._adapter_error(
                        tool="jmeter_run",
                        command="run",
                        error_type="AdapterValidationError",
                        message="JMeter properties must map string names to string values",
                    )
            for name, value in sorted(property_items):
                arguments.extend(("--property", f"{name}={value}"))
            return self._invoke("jmeter_run", "run", arguments)
        finally:
            self._run_lock.release()

    def status(self, *, run_id: str) -> dict[str, Any]:
        return self._invoke("jmeter_status", "status", ("--run-id", run_id))

    def run_details(self, *, run_id: str) -> dict[str, Any]:
        return self._invoke(
            "jmeter_run_details", "run-details", ("--run-id", run_id)
        )

    def jtl_header(self, *, run_id: str) -> dict[str, Any]:
        return self._invoke(
            "jmeter_jtl_header", "jtl-header", ("--run-id", run_id)
        )

    def artifact_manifest(self, *, run_id: str) -> dict[str, Any]:
        return self._invoke(
            "jmeter_artifact_manifest",
            "artifact-manifest",
            ("--run-id", run_id),
        )

    def _invoke(
        self,
        tool: str,
        command: str,
        arguments: Sequence[str] = (),
    ) -> dict[str, Any]:
        cli_command = [
            self.python_executable,
            "-m",
            "jmeter_executor",
            command,
            *arguments,
        ]
        try:
            completed = subprocess.run(
                cli_command,
                cwd=self.working_directory,
                env=self._build_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                close_fds=True,
                check=False,
                timeout=self.cli_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return self._adapter_error(
                tool=tool,
                command=command,
                error_type="AdapterTimeoutError",
                message=(
                    "JMeter CLI exceeded the MCP adapter timeout of "
                    f"{self.cli_timeout_seconds} seconds"
                ),
            )
        except OSError as exc:
            return self._adapter_error(
                tool=tool,
                command=command,
                error_type="AdapterExecutionError",
                message=f"Unable to launch JMeter CLI: {exc}",
            )

        try:
            payload = self._parse_cli_response(completed, command)
        except AdapterProtocolError as exc:
            return self._adapter_error(
                tool=tool,
                command=command,
                error_type=type(exc).__name__,
                message=str(exc),
                cli_exit_code=completed.returncode,
            )

        response: dict[str, Any] = {
            "schema_version": MCP_SCHEMA_VERSION,
            "tool": tool,
            "ok": payload["ok"],
            "executor": {
                "schema_version": payload["schema_version"],
                "command": payload["command"],
                "exit_code": completed.returncode,
            },
        }
        if "result" in payload:
            response["result"] = payload["result"]
        if "error" in payload:
            response["error"] = payload["error"]
        return response

    def _build_environment(self) -> dict[str, str]:
        child = {
            name: self.environment[name]
            for name in _PASSTHROUGH_ENVIRONMENT
            if name in self.environment
        }
        child["JMETER_PROJECT_ROOT"] = str(self.project_root)
        child["PYTHONUNBUFFERED"] = "1"
        return child

    @staticmethod
    def _parse_cli_response(
        completed: subprocess.CompletedProcess[str], expected_command: str
    ) -> dict[str, Any]:
        if completed.stderr:
            raise AdapterProtocolError("JMeter CLI wrote unexpected stderr")
        lines = completed.stdout.splitlines()
        if len(lines) != 1:
            raise AdapterProtocolError("JMeter CLI must emit exactly one JSON line")
        try:
            payload = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            raise AdapterProtocolError("JMeter CLI emitted invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterProtocolError("JMeter CLI response must be a JSON object")
        if payload.get("schema_version") != CLI_SCHEMA_VERSION:
            raise AdapterProtocolError("Unsupported JMeter CLI schema version")
        if payload.get("command") != expected_command:
            raise AdapterProtocolError("JMeter CLI command does not match the request")
        if not isinstance(payload.get("ok"), bool):
            raise AdapterProtocolError("JMeter CLI response is missing boolean ok")
        if payload["ok"] and completed.returncode != 0:
            raise AdapterProtocolError("Successful JMeter CLI response used nonzero exit code")
        if not payload["ok"] and completed.returncode == 0:
            raise AdapterProtocolError("Failed JMeter CLI response used zero exit code")
        if "result" not in payload and "error" not in payload:
            raise AdapterProtocolError("JMeter CLI response has no result or error")
        return payload

    @staticmethod
    def _adapter_error(
        *,
        tool: str,
        command: str,
        error_type: str,
        message: str,
        cli_exit_code: int | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": MCP_SCHEMA_VERSION,
            "tool": tool,
            "ok": False,
            "executor": {
                "schema_version": CLI_SCHEMA_VERSION,
                "command": command,
                "exit_code": cli_exit_code,
            },
            "error": {"type": error_type, "message": message},
        }


def _positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed

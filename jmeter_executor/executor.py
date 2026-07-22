from __future__ import annotations

import csv
import json
import os
import re
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


RUN_ID_RE = re.compile(r"^[a-f0-9]{8,32}$")
PLAN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\.jmx$")
PROPERTY_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
ENVIRONMENT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_INHERITED_ENVIRONMENT = frozenset(
    {
        "HOME",
        "JAVA_HOME",
        "JMETER_HOME",
        "JMETER_OPTS",
        "JRE_HOME",
        "JVM_ARGS",
        "LANG",
        "LC_ALL",
        "PATH",
        "TMPDIR",
        "TZ",
    }
)


class ExecutorError(RuntimeError):
    """Base exception for executor failures."""


class ValidationError(ExecutorError):
    """The requested operation violates the executor boundary."""


class RunConflictError(ExecutorError):
    """A run identifier already has artifacts and cannot be reused."""


class RunNotFoundError(ExecutorError):
    """The requested run does not exist."""


@dataclass(frozen=True)
class ExecutorConfig:
    """Immutable policy and filesystem configuration for a JMeter worker."""

    testplans_dir: Path
    runs_dir: Path
    jmeter_bin: str = "jmeter"
    timeout_seconds: float = 600.0
    terminate_grace_seconds: float = 5.0
    output_limit_chars: int = 4_000
    allowed_properties: frozenset[str] = field(default_factory=frozenset)
    inherited_environment: frozenset[str] = field(
        default_factory=lambda: DEFAULT_INHERITED_ENVIRONMENT
    )
    environment_overrides: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "testplans_dir", Path(self.testplans_dir).resolve())
        object.__setattr__(self, "runs_dir", Path(self.runs_dir).resolve())
        object.__setattr__(self, "allowed_properties", frozenset(self.allowed_properties))
        object.__setattr__(self, "inherited_environment", frozenset(self.inherited_environment))
        object.__setattr__(self, "environment_overrides", dict(self.environment_overrides))

        if not self.jmeter_bin or "\x00" in self.jmeter_bin:
            raise ValueError("jmeter_bin must be a non-empty executable name or path")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.terminate_grace_seconds < 0:
            raise ValueError("terminate_grace_seconds cannot be negative")
        if self.output_limit_chars < 0:
            raise ValueError("output_limit_chars cannot be negative")

        invalid_properties = [
            name for name in self.allowed_properties if not PROPERTY_NAME_RE.fullmatch(name)
        ]
        if invalid_properties:
            raise ValueError(f"Invalid allowed property names: {sorted(invalid_properties)!r}")

        environment_names = set(self.inherited_environment) | set(self.environment_overrides)
        invalid_environment = [
            name for name in environment_names if not ENVIRONMENT_NAME_RE.fullmatch(name)
        ]
        if invalid_environment:
            raise ValueError(f"Invalid environment names: {sorted(invalid_environment)!r}")
        if any(not isinstance(value, str) for value in self.environment_overrides.values()):
            raise ValueError("Environment override values must be strings")
        if any("\x00" in value for value in self.environment_overrides.values()):
            raise ValueError("Environment overrides cannot contain null bytes")

    @classmethod
    def for_project(
        cls,
        base_dir: Path,
        *,
        jmeter_bin: str | None = None,
        timeout_seconds: float = 600.0,
        allowed_properties: Sequence[str] = (),
    ) -> "ExecutorConfig":
        base = Path(base_dir).resolve()
        return cls(
            testplans_dir=base / "testplans",
            runs_dir=base / "reports" / "runs",
            jmeter_bin=jmeter_bin or os.environ.get("JMETER_BIN", "jmeter"),
            timeout_seconds=timeout_seconds,
            allowed_properties=frozenset(allowed_properties),
        )


class JMeterExecutor:
    """Run approved JMX plans inside a confined artifact directory.

    The executor deliberately does not accept raw command-line arguments or target
    URLs. Callers select a checked-in plan and may set only explicitly allowlisted
    JMeter properties. It is synchronous by design; queueing belongs to the later
    orchestration layer.
    """

    def __init__(self, config: ExecutorConfig) -> None:
        self.config = config
        self.config.runs_dir.mkdir(parents=True, exist_ok=True)
        self._assert_directory(self.config.runs_dir, "runs_dir")

    def ping(self) -> dict[str, Any]:
        executable = self._resolve_executable(required=False)
        return {
            "ok": True,
            "executor": "jmeter",
            "jmeter_bin": self.config.jmeter_bin,
            "jmeter_executable": str(executable) if executable else None,
            "jmeter_available": executable is not None,
            "testplans_dir": str(self.config.testplans_dir),
            "runs_dir": str(self.config.runs_dir),
            "timeout_seconds": self.config.timeout_seconds,
            "allowed_properties": sorted(self.config.allowed_properties),
        }

    def list_plans(self) -> dict[str, Any]:
        if not self.config.testplans_dir.is_dir():
            return {"ok": True, "plans": []}

        plans: list[str] = []
        for candidate in self.config.testplans_dir.glob("*.jmx"):
            try:
                plan_path = self._resolve_plan(candidate.name)
            except ValidationError:
                continue
            if plan_path.is_file():
                plans.append(candidate.name)
        return {"ok": True, "plans": sorted(plans)}

    def version(self, *, include_raw: bool = False) -> dict[str, Any]:
        executable = self._resolve_executable(required=True)
        try:
            completed = subprocess.run(
                [str(executable), "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=min(self.config.timeout_seconds, 30.0),
                cwd=self.config.testplans_dir,
                env=self._build_environment(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExecutorError(f"Unable to query JMeter version: {exc}") from exc

        raw = (completed.stdout or "").strip()
        match = re.search(
            r"Apache\s+JMeter.*?(?:version\s*)?\(?\s*([0-9]+(?:\.[0-9]+)+)",
            raw,
            re.IGNORECASE,
        ) or re.search(r"\bversion\s*([0-9]+(?:\.[0-9]+)+)\b", raw, re.IGNORECASE)
        if not match:
            semantic_versions = re.findall(r"(?<!\d)([0-9]+(?:\.[0-9]+){1,2})(?!\d)", raw)
            parsed_version = semantic_versions[-1] if semantic_versions else None
        else:
            parsed_version = match.group(1)

        result: dict[str, Any] = {
            "ok": completed.returncode == 0,
            "version": parsed_version,
            "returncode": completed.returncode,
        }
        if include_raw:
            result["raw"] = raw[: self.config.output_limit_chars]
        return result

    def run(
        self,
        *,
        plan: str,
        run_id: str | None = None,
        properties: Mapping[str, str | int | float | bool] | None = None,
    ) -> dict[str, Any]:
        executable = self._resolve_executable(required=True)
        plan_path = self._resolve_plan(plan)
        if not plan_path.is_file():
            raise ValidationError(f"Plan not found: {plan}")

        validated_properties = self._validate_properties(properties or {})
        rid = self.validate_run_id(run_id or uuid.uuid4().hex[:12])
        paths = self.run_paths(rid)
        run_dir = paths["run_dir"]

        try:
            run_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise RunConflictError(f"Run already exists: {rid}") from exc

        command = [
            str(executable),
            "-n",
            "-t",
            str(plan_path),
            "-l",
            str(paths["jtl_path"]),
            "-j",
            str(paths["log_path"]),
            "-e",
            "-o",
            str(paths["html_dir"]),
        ]
        command.extend(f"-J{name}={value}" for name, value in sorted(validated_properties.items()))

        started_at = time.time()
        metadata: dict[str, Any] = {
            "run_id": rid,
            "plan": plan_path.name,
            "plan_path": str(plan_path),
            "started_at": started_at,
            "started_at_iso": self._iso_timestamp(started_at),
            "status": "running",
            "command": self._redacted_command(command),
            "property_names": sorted(validated_properties),
        }
        self._write_metadata(paths["meta_path"], metadata)

        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                shell=False,
                start_new_session=os.name != "nt",
                cwd=self.config.testplans_dir,
                env=self._build_environment(),
                close_fds=True,
            )
            metadata["pid"] = process.pid
            self._write_metadata(paths["meta_path"], metadata)
            stdout, stderr = process.communicate(timeout=self.config.timeout_seconds)
            finished_at = time.time()
            status = "completed" if process.returncode == 0 else "failed"
            metadata.update(
                {
                    "finished_at": finished_at,
                    "finished_at_iso": self._iso_timestamp(finished_at),
                    "duration_seconds": round(finished_at - started_at, 6),
                    "returncode": process.returncode,
                    "status": status,
                    "stdout": self._sanitize_output(stdout, validated_properties),
                    "stderr": self._sanitize_output(stderr, validated_properties),
                    **self._artifact_metadata(paths),
                }
            )
        except subprocess.TimeoutExpired:
            assert process is not None
            self._terminate_process_tree(process)
            stdout, stderr = process.communicate()
            finished_at = time.time()
            metadata.update(
                {
                    "finished_at": finished_at,
                    "finished_at_iso": self._iso_timestamp(finished_at),
                    "duration_seconds": round(finished_at - started_at, 6),
                    "returncode": process.returncode,
                    "status": "timed_out",
                    "stdout": self._sanitize_output(stdout, validated_properties),
                    "stderr": self._sanitize_output(stderr, validated_properties),
                    "error": f"JMeter exceeded timeout of {self.config.timeout_seconds} seconds",
                    **self._artifact_metadata(paths),
                }
            )
        except OSError as exc:
            finished_at = time.time()
            metadata.update(
                {
                    "finished_at": finished_at,
                    "finished_at_iso": self._iso_timestamp(finished_at),
                    "duration_seconds": round(finished_at - started_at, 6),
                    "status": "error",
                    "error": str(exc),
                    **self._artifact_metadata(paths),
                }
            )

        self._write_metadata(paths["meta_path"], metadata)
        return self._public_run(metadata, paths)

    def get_run(self, run_id: str) -> dict[str, Any]:
        paths = self.run_paths(run_id)
        metadata = self._read_metadata(paths["meta_path"])
        return {"ok": True, **metadata, **self._artifact_metadata(paths)}

    def get_run_summary(self, run_id: str) -> dict[str, Any]:
        paths = self.run_paths(run_id)
        metadata = self._read_metadata(paths["meta_path"])
        return self._public_run(metadata, paths)

    def get_jtl_header(self, run_id: str) -> dict[str, Any]:
        paths = self.run_paths(run_id)
        self._read_metadata(paths["meta_path"])
        jtl_path = paths["jtl_path"]
        if not jtl_path.is_file():
            raise RunNotFoundError(f"JTL artifact not found for run: {run_id}")

        try:
            with jtl_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                columns = next(csv.reader(handle), None)
        except OSError as exc:
            raise ExecutorError(f"Unable to read JTL for run {run_id}: {exc}") from exc

        if not columns:
            raise ExecutorError(f"JTL artifact is empty for run: {run_id}")
        return {
            "ok": True,
            "run_id": self.validate_run_id(run_id),
            "jtl_path": str(jtl_path),
            "columns": [column.strip() for column in columns],
        }

    def run_paths(self, run_id: str) -> dict[str, Path]:
        rid = self.validate_run_id(run_id)
        run_dir = self.config.runs_dir / rid
        self._assert_within(run_dir, self.config.runs_dir, "run directory")
        return {
            "run_dir": run_dir,
            "jtl_path": run_dir / "results.jtl",
            "log_path": run_dir / "jmeter.log",
            "html_dir": run_dir / "html",
            "meta_path": run_dir / "run.json",
        }

    @staticmethod
    def validate_run_id(run_id: str) -> str:
        candidate = (run_id or "").strip()
        if not RUN_ID_RE.fullmatch(candidate):
            raise ValidationError("run_id must contain 8-32 lowercase hexadecimal characters")
        return candidate

    def _resolve_plan(self, plan: str) -> Path:
        candidate = (plan or "").strip()
        if not PLAN_NAME_RE.fullmatch(candidate):
            raise ValidationError("plan must be a simple .jmx filename")
        plan_path = (self.config.testplans_dir / candidate).resolve()
        self._assert_within(plan_path, self.config.testplans_dir, "test plan")
        return plan_path

    def _validate_properties(
        self, properties: Mapping[str, str | int | float | bool]
    ) -> dict[str, str]:
        validated: dict[str, str] = {}
        for raw_name, raw_value in properties.items():
            name = str(raw_name)
            if not PROPERTY_NAME_RE.fullmatch(name):
                raise ValidationError(f"Invalid JMeter property name: {name!r}")
            if name not in self.config.allowed_properties:
                raise ValidationError(f"JMeter property is not allowlisted: {name}")
            if not isinstance(raw_value, (str, int, float, bool)):
                raise ValidationError(f"Unsupported value type for JMeter property: {name}")
            value = str(raw_value).lower() if isinstance(raw_value, bool) else str(raw_value)
            if "\x00" in value or "\r" in value or "\n" in value:
                raise ValidationError(f"Invalid control character in JMeter property: {name}")
            if len(value) > 2_048:
                raise ValidationError(f"JMeter property value is too long: {name}")
            validated[name] = value
        return validated

    def _resolve_executable(self, *, required: bool) -> Path | None:
        executable = shutil.which(self.config.jmeter_bin)
        if executable:
            return Path(executable).resolve()

        configured = Path(self.config.jmeter_bin)
        if configured.is_absolute() and configured.is_file() and os.access(configured, os.X_OK):
            return configured.resolve()
        if required:
            raise ExecutorError(f"JMeter executable not found: {self.config.jmeter_bin}")
        return None

    def _build_environment(self) -> dict[str, str]:
        environment = {
            name: os.environ[name]
            for name in self.config.inherited_environment
            if name in os.environ
        }
        environment.update(self.config.environment_overrides)
        return environment

    def _terminate_process_tree(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=self.config.terminate_grace_seconds)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait()
        except ProcessLookupError:
            pass

    def _read_metadata(self, meta_path: Path) -> dict[str, Any]:
        if not meta_path.is_file():
            raise RunNotFoundError(f"Unknown run_id: {meta_path.parent.name}")
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExecutorError(f"Invalid run metadata: {meta_path}") from exc
        if not isinstance(data, dict):
            raise ExecutorError(f"Invalid run metadata object: {meta_path}")
        return data

    @staticmethod
    def _write_metadata(meta_path: Path, metadata: Mapping[str, Any]) -> None:
        temporary = meta_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, meta_path)

    @staticmethod
    def _assert_directory(path: Path, label: str) -> None:
        if path.is_symlink() or not path.is_dir():
            raise ValidationError(f"{label} must be a real directory: {path}")

    @staticmethod
    def _assert_within(path: Path, root: Path, label: str) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValidationError(f"{label} escapes its configured root") from exc

    def _artifact_metadata(self, paths: Mapping[str, Path]) -> dict[str, Any]:
        return {
            "jtl_path": str(paths["jtl_path"]),
            "log_path": str(paths["log_path"]),
            "html_dir": str(paths["html_dir"]),
            "jtl_exists": paths["jtl_path"].is_file(),
            "log_exists": paths["log_path"].is_file(),
            "html_exists": paths["html_dir"].is_dir(),
        }

    def _public_run(self, metadata: Mapping[str, Any], paths: Mapping[str, Path]) -> dict[str, Any]:
        status = str(metadata.get("status", "unknown"))
        return {
            "ok": status == "completed",
            "run_id": metadata.get("run_id"),
            "status": status,
            "plan": metadata.get("plan"),
            "started_at": metadata.get("started_at"),
            "finished_at": metadata.get("finished_at"),
            "duration_seconds": metadata.get("duration_seconds"),
            "returncode": metadata.get("returncode"),
            "error": metadata.get("error"),
            **self._artifact_metadata(paths),
        }

    def _redacted_command(self, command: Sequence[str]) -> list[str]:
        redacted: list[str] = []
        for argument in command:
            if argument.startswith("-J") and "=" in argument:
                name = argument[2:].split("=", 1)[0]
                redacted.append(f"-J{name}=<redacted>")
            else:
                redacted.append(argument)
        return redacted

    def _truncate(self, value: str | None) -> str:
        return (value or "")[: self.config.output_limit_chars]

    def _sanitize_output(self, value: str | None, properties: Mapping[str, str]) -> str:
        sanitized = value or ""
        for property_value in sorted(properties.values(), key=len, reverse=True):
            if property_value:
                sanitized = sanitized.replace(property_value, "<redacted>")
        return self._truncate(sanitized)

    @staticmethod
    def _iso_timestamp(value: float) -> str:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()

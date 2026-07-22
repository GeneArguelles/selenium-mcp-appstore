"""Machine-readable command line interface for the isolated JMeter executor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from .executor import (
    ExecutorConfig,
    ExecutorError,
    JMeterExecutor,
    RunConflictError,
    RunNotFoundError,
    ValidationError,
)


SCHEMA_VERSION = "pe.jmeter.cli.v1"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_CONFLICT = 4
EXIT_EXECUTOR_ERROR = 5
EXIT_RUN_FAILED = 10


class CliUsageError(ValueError):
    """The CLI request is syntactically invalid."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Convert argparse failures into the CLI's JSON error contract."""

    def error(self, message: str) -> None:
        raise CliUsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog="jmeter-executor",
        description="Execute approved JMeter plans and emit one JSON response.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ping", help="Inspect executor configuration and availability")

    version_parser = subparsers.add_parser("version", help="Return the JMeter version")
    version_parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include bounded raw JMeter version output in the JSON result",
    )

    subparsers.add_parser("list-plans", help="List approved JMX plans")

    run_parser = subparsers.add_parser("run", help="Run an approved JMX plan synchronously")
    run_parser.add_argument("--plan", required=True, help="Approved .jmx filename")
    run_parser.add_argument(
        "--run-id",
        help="Optional 8-32 character lowercase hexadecimal run identifier",
    )
    run_parser.add_argument(
        "--property",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Repeatable, deployment-allowlisted JMeter property",
    )

    status_parser = subparsers.add_parser("status", help="Return a run summary")
    status_parser.add_argument("--run-id", required=True)

    details_parser = subparsers.add_parser("run-details", help="Return stored run metadata")
    details_parser.add_argument("--run-id", required=True)

    header_parser = subparsers.add_parser("jtl-header", help="Return JTL CSV columns")
    header_parser.add_argument("--run-id", required=True)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    output: TextIO | None = None,
) -> int:
    environment = dict(os.environ if environ is None else environ)
    stream = sys.stdout if output is None else output
    command = _command_hint(argv)

    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
        command = args.command
        executor = _build_executor(environment)
        result = _dispatch(executor, args)
        operation_ok = True
        exit_code = EXIT_OK
        if command == "run" and not result.get("ok", False):
            operation_ok = False
            exit_code = EXIT_RUN_FAILED
        elif command == "version" and not result.get("ok", False):
            operation_ok = False
            exit_code = EXIT_EXECUTOR_ERROR
        _emit(stream, command=command, ok=operation_ok, result=result)
        return exit_code
    except CliUsageError as exc:
        _emit_error(stream, command, exc)
        return EXIT_USAGE
    except ValidationError as exc:
        _emit_error(stream, command, exc)
        return EXIT_USAGE
    except RunNotFoundError as exc:
        _emit_error(stream, command, exc)
        return EXIT_NOT_FOUND
    except RunConflictError as exc:
        _emit_error(stream, command, exc)
        return EXIT_CONFLICT
    except (ExecutorError, ValueError) as exc:
        _emit_error(stream, command, exc)
        return EXIT_EXECUTOR_ERROR
    except Exception as exc:  # pragma: no cover - last-resort JSON boundary
        _emit_error(stream, command, RuntimeError(str(exc)), error_type="InternalError")
        return EXIT_EXECUTOR_ERROR


def _build_executor(environment: Mapping[str, str]) -> JMeterExecutor:
    default_root = Path(__file__).resolve().parents[1]
    project_root = Path(environment.get("JMETER_PROJECT_ROOT", str(default_root)))

    timeout_text = environment.get("JMETER_TIMEOUT_SECONDS", "600")
    try:
        timeout_seconds = float(timeout_text)
    except ValueError as exc:
        raise ValueError("JMETER_TIMEOUT_SECONDS must be numeric") from exc

    allowed_properties = tuple(
        name.strip()
        for name in environment.get("JMETER_ALLOWED_PROPERTIES", "").split(",")
        if name.strip()
    )
    config = ExecutorConfig.for_project(
        project_root,
        jmeter_bin=environment.get("JMETER_BIN"),
        timeout_seconds=timeout_seconds,
        allowed_properties=allowed_properties,
    )
    return JMeterExecutor(config)


def _dispatch(executor: JMeterExecutor, args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "ping":
        return executor.ping()
    if args.command == "version":
        return executor.version(include_raw=args.include_raw)
    if args.command == "list-plans":
        return executor.list_plans()
    if args.command == "run":
        return executor.run(
            plan=args.plan,
            run_id=args.run_id,
            properties=_parse_properties(args.property),
        )
    if args.command == "status":
        return executor.get_run_summary(args.run_id)
    if args.command == "run-details":
        return executor.get_run(args.run_id)
    if args.command == "jtl-header":
        return executor.get_jtl_header(args.run_id)
    raise CliUsageError(f"Unsupported command: {args.command}")


def _parse_properties(items: Sequence[str]) -> dict[str, str]:
    properties: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise CliUsageError("--property must use NAME=VALUE syntax")
        name, value = item.split("=", 1)
        if not name:
            raise CliUsageError("--property name cannot be empty")
        if name in properties:
            raise CliUsageError(f"Duplicate --property name: {name}")
        properties[name] = value
    return properties


def _emit(
    stream: TextIO,
    *,
    command: str,
    ok: bool,
    result: Mapping[str, Any],
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "ok": ok,
        "result": result,
    }
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()


def _emit_error(
    stream: TextIO,
    command: str,
    exc: Exception,
    *,
    error_type: str | None = None,
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "error": {
            "type": error_type or type(exc).__name__,
            "message": str(exc),
        },
    }
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()


def _command_hint(argv: Sequence[str] | None) -> str:
    arguments = list(sys.argv[1:] if argv is None else argv)
    for argument in arguments:
        if argument and not argument.startswith("-"):
            return argument
    return "unknown"

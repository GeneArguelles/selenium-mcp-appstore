"""Compatibility adapter for the isolated JMeter executor.

New code should depend on :mod:`jmeter_executor` directly. These functions keep
the existing FastAPI routes working while rejecting the former raw ``extra_args``
surface.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from jmeter_executor import ExecutorConfig, ExecutorError, JMeterExecutor


BASE_DIR = Path(__file__).resolve().parents[1]
TESTPLANS_DIR = (BASE_DIR / "testplans").resolve()
REPORTS_DIR = (BASE_DIR / "reports").resolve()
RUNS_DIR = (REPORTS_DIR / "runs").resolve()

_ALLOWED_PROPERTIES = tuple(
    name.strip()
    for name in os.environ.get("JMETER_ALLOWED_PROPERTIES", "").split(",")
    if name.strip()
)
_EXECUTOR = JMeterExecutor(
    ExecutorConfig.for_project(
        BASE_DIR,
        timeout_seconds=float(os.environ.get("JMETER_TIMEOUT_SECONDS", "600")),
        allowed_properties=_ALLOWED_PROPERTIES,
    )
)


def _error_response(exc: ExecutorError) -> dict[str, Any]:
    return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}


def ping() -> dict[str, Any]:
    return _EXECUTOR.ping()


def list_plans() -> dict[str, Any]:
    return _EXECUTOR.list_plans()


def jmeter_version(raw: bool = False) -> dict[str, Any]:
    try:
        return _EXECUTOR.version(include_raw=raw)
    except ExecutorError as exc:
        return _error_response(exc)


def run_test(
    plan: str,
    run_id: str | None = None,
    extra_args: Sequence[str] | None = None,
    properties: Mapping[str, str | int | float | bool] | None = None,
) -> dict[str, Any]:
    if extra_args:
        return {
            "ok": False,
            "error": "Raw JMeter extra_args are disabled; use approved properties",
            "error_type": "ValidationError",
        }
    try:
        return _EXECUTOR.run(plan=plan, run_id=run_id, properties=properties)
    except ExecutorError as exc:
        return _error_response(exc)


def get_run(run_id: str) -> dict[str, Any]:
    try:
        return _EXECUTOR.get_run(run_id)
    except ExecutorError as exc:
        return _error_response(exc)


def run_status(run_id: str) -> dict[str, Any]:
    return get_run_summary(run_id)


def get_run_summary(run_id: str) -> dict[str, Any]:
    try:
        return _EXECUTOR.get_run_summary(run_id)
    except ExecutorError as exc:
        return _error_response(exc)


def get_jtl_header(run_id: str) -> dict[str, Any]:
    try:
        return _EXECUTOR.get_jtl_header(run_id)
    except ExecutorError as exc:
        return _error_response(exc)


def _run_paths(run_id: str) -> dict[str, Path]:
    """Temporary compatibility hook used by the existing report routes."""
    return _EXECUTOR.run_paths(run_id)

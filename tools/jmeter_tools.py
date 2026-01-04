from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import time
import uuid
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_RUN_ID_RE = re.compile(r"^[a-f0-9]{8,32}$")

BASE_DIR = Path(__file__).resolve().parents[1]
TESTPLANS_DIR = (BASE_DIR / "testplans").resolve()
REPORTS_DIR = (BASE_DIR / "reports").resolve()
RUNS_DIR = (REPORTS_DIR / "runs").resolve()

JMETER_BIN = os.environ.get("JMETER_BIN", "jmeter")

def _safe_run_id(run_id: str) -> str:
    run_id = (run_id or "").strip()
    if not _RUN_ID_RE.match(run_id):
        raise ValueError("Invalid run_id")
    return run_id

def ping() -> Dict[str, Any]:
    return {
        "ok": True,
        "module": "tools.jmeter_tools",
        "jmeter_bin": JMETER_BIN,
        "jmeter_on_path": shutil.which(JMETER_BIN) is not None,
        "testplans_dir": str(TESTPLANS_DIR),
        "reports_dir": str(REPORTS_DIR),
        "runs_dir": str(RUNS_DIR),
    }


def list_plans() -> Dict[str, Any]:
    if not TESTPLANS_DIR.exists():
        return {"plans": []}
    return {"plans": sorted(p.name for p in TESTPLANS_DIR.glob("*.jmx"))}


def jmeter_version():
    p = subprocess.run(
        ["jmeter", "-v"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    out = (p.stdout or "").strip()

    # Extract "5.6.3" from: Apache JMeter (version 5.6.3)
    m = re.search(r"Apache JMeter\s*\(version\s*([0-9.]+)", out)
    version = m.group(1) if m else None

    return {
        "ok": True,
        "version": version,
    }


def _safe_name(name: str) -> str:
    name = name.strip().replace("\\", "/")
    if "/" in name or ".." in name:
        raise ValueError("Invalid plan name")
    if not name.lower().endswith(".jmx"):
        raise ValueError("Plan must be a .jmx file")
    return name


def _run_paths(run_id: str) -> dict:
    run_dir = RUNS_DIR / run_id
    return {
        "run_dir": run_dir,
        "jtl_path": run_dir / "results.jtl",
        "log_path": run_dir / "jmeter.log",
        "html_dir": run_dir / "html",
        "meta_path": run_dir / "run.json",
    }


def _write_meta(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _read_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_test(plan: str, run_id: Optional[str] = None, extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run a JMeter test plan in non-GUI mode (synchronous).
    Produces:
      reports/runs/<run_id>/{results.jtl,jmeter.log,html/,run.json}
    """
    env_plan = _safe_name(plan)
    plan_path = (TESTPLANS_DIR / env_plan).resolve()

    if not plan_path.exists():
        return {"ok": False, "error": f"Plan not found: {env_plan}", "plans_dir": str(TESTPLANS_DIR)}

    exe = shutil.which(JMETER_BIN)
    if not exe:
        return {"ok": False, "error": f"JMeter executable not found: {JMETER_BIN}"}

    rid = run_id or uuid.uuid4().hex[:12]
    paths = _run_paths(rid)
    run_dir: Path = paths["run_dir"]
    jtl_path: Path = paths["jtl_path"]
    log_path: Path = paths["log_path"]
    html_dir: Path = paths["html_dir"]
    meta_path: Path = paths["meta_path"]

    run_dir.mkdir(parents=True, exist_ok=True)
    if html_dir.exists():
        shutil.rmtree(html_dir)

    cmd = [
        exe,
        "-n",
        "-t",
        str(plan_path),
        "-l",
        str(jtl_path),
        "-j",
        str(log_path),
        "-e",
        "-o",
        str(html_dir),
    ]
    if extra_args:
        cmd.extend(extra_args)

    meta = {
        "run_id": rid,
        "plan": env_plan,
        "plan_path": str(plan_path),
        "started_at": time.time(),
        "cmd": cmd,
        "status": "running",
    }
    _write_meta(meta_path, meta)

    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 10)
        meta.update(
            {
                "finished_at": time.time(),
                "returncode": cp.returncode,
                "status": "ok" if cp.returncode == 0 else "failed",
                "stdout": (cp.stdout or "")[:4000],
                "stderr": (cp.stderr or "")[:4000],
                "jtl_path": str(jtl_path),
                "log_path": str(log_path),
                "html_dir": str(html_dir),
            }
        )
        _write_meta(meta_path, meta)

        return {
            "ok": cp.returncode == 0,
            "run_id": rid,
            "status": meta["status"],
            "returncode": cp.returncode,
            "jtl_path": str(jtl_path),
            "log_path": str(log_path),
            "html_dir": str(html_dir),
        }
    except subprocess.TimeoutExpired:
        meta.update({"finished_at": time.time(), "status": "timeout"})
        _write_meta(meta_path, meta)
        return {"ok": False, "run_id": rid, "status": "timeout", "error": "JMeter run timed out"}
    except Exception as e:
        meta.update({"finished_at": time.time(), "status": "error", "error": str(e)})
        _write_meta(meta_path, meta)
        return {"ok": False, "run_id": rid, "status": "error", "error": str(e)}


def get_run(run_id: str) -> Dict[str, Any]:
    paths = _run_paths(run_id)
    meta = _read_meta(paths["meta_path"])
    if not meta:
        return {"ok": False, "error": f"Unknown run_id: {run_id}"}
    return {"ok": True, **meta}


def get_run_summary(run_id: str) -> Dict[str, Any]:
    paths = _run_paths(run_id)
    meta = _read_meta(paths["meta_path"])
    if not meta:
        return {"ok": False, "error": f"Unknown run_id: {run_id}"}

    return {
        "ok": True,
        "run_id": run_id,
        "status": meta.get("status"),
        "returncode": meta.get("returncode"),
        "plan": meta.get("plan"),
        "html_dir": str(paths["html_dir"]),
        "jtl_path": str(paths["jtl_path"]),
        "log_path": str(paths["log_path"]),
        "jtl_exists": paths["jtl_path"].exists(),
        "html_exists": paths["html_dir"].exists(),
    }

def get_jtl_header(run_id: str) -> Dict[str, Any]:
    """
    Return the header row of the JTL (CSV) produced by a run.
    """
    paths = _run_paths(run_id)
    jtl_path: Path = paths["jtl_path"]

    if not jtl_path.exists():
        return {
            "ok": False,
            "run_id": run_id,
            "error": "results.jtl not found",
            "jtl_path": str(jtl_path),
        }

    try:
        # Read only the first line (header)
        with jtl_path.open("r", encoding="utf-8", errors="replace") as f:
            header_line = f.readline().strip("\r\n")

        if not header_line:
            return {
                "ok": False,
                "run_id": run_id,
                "error": "results.jtl is empty (no header line)",
                "jtl_path": str(jtl_path),
            }

        # Split CSV header into columns (simple split is fine for JMeter's header)
        columns = [c.strip() for c in header_line.split(",") if c.strip()]

        return {
            "ok": True,
            "run_id": run_id,
            "jtl_path": str(jtl_path),
            "header_line": header_line,
            "columns": columns,
        }

    except Exception as e:
        return {
            "ok": False,
            "run_id": run_id,
            "error": str(e),
            "jtl_path": str(jtl_path),
        }
# Isolated JMeter Executor

`jmeter_executor` is the execution boundary between Persona Engineering control
logic and Apache JMeter. It runs approved, local `.jmx` plans and writes each run
to an immutable artifact directory.

## Security invariants

- Plans must be simple `.jmx` filenames confined to `testplans_dir`.
- Run IDs are 8-32 lowercase hexadecimal characters.
- Existing run directories are never deleted or reused.
- Raw JMeter arguments, filesystem paths, and target URLs are not accepted.
- Runtime properties must be explicitly allowlisted by trusted configuration.
- Property values are redacted from stored commands and process output.
- The worker receives a small allowlist of parent environment variables, not the
  complete application environment.
- JMeter runs without a shell, without standard input, in a fixed working
  directory, and in a separate process session.
- Timed-out process groups are terminated and, if necessary, killed.
- Run metadata is written atomically.

## Direct use

```python
from pathlib import Path

from jmeter_executor import ExecutorConfig, JMeterExecutor

executor = JMeterExecutor(
    ExecutorConfig.for_project(
        Path.cwd(),
        allowed_properties=("threads", "ramp_seconds"),
    )
)

result = executor.run(
    plan="httpbin_smoke.jmx",
    properties={"threads": 1, "ramp_seconds": 1},
)
```

The executor is intentionally synchronous. Job queueing, cancellation APIs,
Ledger events, assessment, and report publication belong to the Persona
Engineering orchestration layer and are not implemented here.

`tools/jmeter_tools.py` is retained temporarily as a compatibility adapter for
the repository's existing FastAPI routes. New code should import
`jmeter_executor` directly.

## Machine-readable CLI

The supported automation boundary is `python -m jmeter_executor` (or the
installed `jmeter-executor` console command). Every operational command writes
exactly one compact JSON object to standard output. Errors use the same envelope
and do not write argparse usage text to standard error.

```bash
python -m jmeter_executor ping
python -m jmeter_executor version
python -m jmeter_executor list-plans
python -m jmeter_executor run --plan httpbin_smoke.jmx --run-id deadbeef
python -m jmeter_executor status --run-id deadbeef
python -m jmeter_executor run-details --run-id deadbeef
python -m jmeter_executor jtl-header --run-id deadbeef
python -m jmeter_executor artifact-manifest --run-id deadbeef
```

Runtime configuration is supplied by the trusted worker environment rather than
by caller-controlled path flags:

- `JMETER_PROJECT_ROOT`
- `JMETER_BIN`
- `JMETER_TIMEOUT_SECONDS`
- `JMETER_ALLOWED_PROPERTIES` (comma-separated)

`--property NAME=VALUE` is repeatable, but a name is accepted only when it is in
`JMETER_ALLOWED_PROPERTIES`. Property values must contain non-secret performance
parameters because JMeter receives them as process arguments.

## Persona Engineering MCP adapter

The canonical FastMCP server in `mcp_server_v2.py` exposes nine constrained
JMeter tools through `JMeterMcpAdapter`:

```text
jmeter_ping
jmeter_version
jmeter_list_plans
jmeter_run
jmeter_status
jmeter_run_details
jmeter_jtl_header
jmeter_artifact_manifest
jmeter_metrics_summary
```

The adapter launches `python -m jmeter_executor` without a shell, supplies only a
small environment allowlist, validates the CLI schema and exit-code consistency,
and wraps the response as `pe.jmeter.mcp.v1`. A single server process accepts at
most one active `jmeter_run`; a concurrent request receives a structured
`RunBusyError` instead of joining an unbounded queue.

Example successful MCP tool result:

```json
{
  "schema_version": "pe.jmeter.mcp.v1",
  "tool": "jmeter_run",
  "ok": true,
  "executor": {
    "schema_version": "pe.jmeter.cli.v1",
    "command": "run",
    "exit_code": 0
  },
  "result": {
    "run_id": "ca110002",
    "status": "completed"
  }
}
```

`JMETER_MCP_TIMEOUT_SECONDS` controls the outer adapter timeout and defaults to
`JMETER_TIMEOUT_SECONDS + 30`. Executor configuration remains deployment-owned;
none of these settings can be changed by an MCP tool request.

`jmeter_artifact_manifest` returns the executor-computed SHA-256 digest and byte
size for the approved JMX plan, JTL results, JMeter log, dashboard entry point,
and final `run.json`. Missing artifacts are represented explicitly with
`exists: false`; hash values are never fabricated. The evidence payload is
versioned as `pe.jmeter.evidence.v1` for ingestion by the Persona Engineering
Ledger.

`jmeter_metrics_summary` parses the immutable JTL artifact and returns the
versioned `pe.jmeter.metrics.v1` contract. It includes sample/success/error
counts, error rate, approximate wall duration, throughput, byte totals,
response-code and label counts, plus min/mean/median/p90/p95/p99/max
distributions for elapsed, latency, and connect time. Percentiles use the
deterministic nearest-rank method. The response includes the source JTL SHA-256
so PE can bind every assessment to the exact evidence artifact.

The JSON envelope is versioned as `pe.jmeter.cli.v1`. Exit codes are stable:

| Code | Meaning |
| ---: | --- |
| `0` | CLI operation completed |
| `2` | Usage, validation, or policy error |
| `3` | Run not found |
| `4` | Run ID already exists |
| `5` | Executor/configuration failure |
| `10` | JMeter ran but returned a non-success terminal state |

## Docker smoke test

The pull-request workflow builds the actual runtime image and runs both the
unit suite and `scripts/run_jmeter_smoke.py` inside it. The smoke test starts a
local HTTP target, executes `httpbin_smoke.jmx` through the JSON CLI and the
installed JMeter binary, then verifies the resulting JTL, log, and HTML
dashboard. It does not depend on `httpbin.org` or another public test service.

To run the same checks locally where Docker is installed:

```bash
docker build --tag selenium-mcp-jmeter-smoke .
docker run --rm --entrypoint python selenium-mcp-jmeter-smoke \
  -m unittest discover -s tests -v
docker run --rm --entrypoint python selenium-mcp-jmeter-smoke \
  scripts/run_jmeter_smoke.py
```

The workflow also executes `scripts/run_blazedemo_plan_smoke.py`. That check
runs the complete `blazedemo_booking_smoke.jmx` journey against a deterministic
local fixture and verifies 24 successful samples, per-step counts, evidence
hash binding, and the machine-readable metrics summary. It deliberately does
not send CI traffic to the public BlazeDemo service.

## Governed BlazeDemo smoke test

`testplans/blazedemo_booking_smoke.jmx` models a bounded four-request booking
journey:

1. Open the home page.
2. Search Boston to London.
3. Select a fixed demonstration flight.
4. Submit a synthetic purchase and verify confirmation.

The plan runs three threads, two iterations, a six-second ramp, and a 750 ms
pacing delay: 24 total samples. Every response must return HTTP 200 and contain
the expected page marker. Embedded resources are disabled. The purchase data is
fixed and synthetic; never substitute real personal or payment information.

The public run must be ordered through the Persona Engineering performance-test
harness so the request, execution, evidence hashes, assessment, and reports are
Ledger-bound. It is a functional/performance smoke test, not a load, stress, or
capacity test. Follow
`jmeter_executor/BLAZEDEMO_SMOKE_RUNBOOK.md`.

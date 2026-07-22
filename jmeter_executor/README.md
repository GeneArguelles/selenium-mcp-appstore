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

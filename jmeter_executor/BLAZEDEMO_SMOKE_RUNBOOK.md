# Governed BlazeDemo Booking Smoke Test

This runbook executes the checked-in `blazedemo_booking_smoke.jmx` plan against
`https://blazedemo.com` through the complete Persona Engineering path:

```text
PE harness -> MCP adapter -> JMeter CLI -> isolated executor
          -> metrics assessor -> evidence Ledger -> JSON/Markdown reports
```

BlazeDemo identifies itself as a sample travel site for performance-testing
demonstrations. Keep this run bounded. Do not turn it into a load, stress,
soak, spike, or capacity test without explicit authorization from the target
owner.

## Traffic and assertions

| Item | Value |
| --- | --- |
| Virtual users | 3 |
| Iterations per user | 2 |
| Requests per journey | 4 |
| Total samples | 24 |
| Ramp | 6 seconds |
| Pacing | 750 ms between requests |
| Maximum scheduled duration | 90 seconds |
| Embedded resources | Disabled |
| Test data | Fixed synthetic values only |

The journey validates the home, route search, flight selection, and purchase
confirmation pages with both HTTP status and response-content assertions.

## Assessment policy

Use the versioned smoke-test policy below:

| Check | Threshold |
| --- | ---: |
| Minimum sample count | 24 |
| Maximum error rate | 0 |
| Maximum p95 elapsed time | 2,000 ms |
| Minimum throughput | 0.25 samples/second |

Public-network latency can vary. A latency or throughput failure means the run
did not satisfy this policy at that time; it does not by itself diagnose
BlazeDemo capacity.

## 1. Build and start the MCP/JMeter service

From the `selenium-mcp-appstore` repository:

```bash
cd /Users/genea1/projects/appstore/selenium-mcp-appstore

docker build --tag selenium-mcp-jmeter-pe:local .

docker run --rm --detach \
  --name jmeter-mcp-pe \
  --publish 127.0.0.1:8000:8000 \
  --volume /Users/genea1/projects/appstore/selenium-mcp-appstore/reports/runs:/app/reports/runs \
  --env HOST=0.0.0.0 \
  --env PORT=8000 \
  --env JMETER_TIMEOUT_SECONDS=120 \
  --env JMETER_MCP_TIMEOUT_SECONDS=150 \
  --env JMETER_ALLOWED_PROPERTIES=smoke_host,smoke_port,smoke_protocol \
  selenium-mcp-jmeter-pe:local
```

Confirm readiness:

```bash
curl --fail --silent http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## 2. Order the live smoke test through Persona Engineering

From the `PersonaEngineering` repository:

```bash
cd /Users/genea1/PersonaEngineering

RUN_ID="$(python3 -c 'import secrets; print(secrets.token_hex(4))')"

python3 -m performance_test_harness run \
  --plan blazedemo_booking_smoke.jmx \
  --run-id "$RUN_ID" \
  --property smoke_host=blazedemo.com \
  --property smoke_protocol=https \
  --policy-id pe.jmeter.blazedemo.smoke.v1 \
  --min-sample-count 24 \
  --max-error-rate 0 \
  --max-p95-elapsed-ms 2000 \
  --min-throughput-per-second 0.25
```

The result is operationally successful when `ok` is `true` and `status` is
`completed`. It satisfies the performance policy only when
`performance_accepted` is `true` and `assessment_verdict` is `pass`.

## 3. Verify evidence and open the reports

```bash
python3 -m performance_test_harness verify-ledger

python3 -m json.tool \
  "reports/performance/jmeter_performance_${RUN_ID}.json"

open "reports/performance/jmeter_performance_${RUN_ID}.md"
```

The report binds the requested plan, metrics, assessment verdict, artifact
SHA-256 values, and terminal Ledger event. The executor artifacts are under:

```text
/Users/genea1/projects/appstore/selenium-mcp-appstore/reports/runs/<run_id>/
```

## 4. Stop the local service

```bash
docker stop jmeter-mcp-pe
```

If a run fails, preserve the run ID and inspect the JSON report, JTL, JMeter
log, and Ledger terminal event before retrying. Never reuse an existing run ID.

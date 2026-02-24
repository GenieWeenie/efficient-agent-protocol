# Operator Telemetry Pack (EAP-081)

This pack exports dashboard-ready telemetry so maintainers can diagnose failures from artifacts alone.

## Export Command

```bash
python3 scripts/export_telemetry_pack.py \
  --db-path agent_state.db \
  --output-dir artifacts/telemetry
```

Optional:

- `--limit-runs 500` (default)
- `--failed-run-id <run_id>` to force diagnosis focus on one run

## Artifacts

The exporter writes:

- `overview.json`
  - run totals, failure rate, retry totals
  - aggregate latency percentiles
  - aggregate saturation metrics
- `retries.json`
  - retry counts by tool, step, and run
- `fail_reasons.json`
  - failure counts by `error_type`
  - top failure tools/messages
  - recent failure events
- `latency_percentiles.json`
  - overall and per-tool latency (`p50/p95/p99/max`)
- `saturation.json`
  - aggregate and per-run saturation metrics
  - includes wait times and rate-limit pressure
- `failed_run_diagnostics.json`
  - run summary
  - root failure event
  - event timeline
  - dependency cascade count
- `operator_report.md`
  - compact triage report with recommended actions
- `manifest.json`
  - generation metadata and file list

## Diagnostic Workflow

1. Open `operator_report.md` for quick triage.
2. Confirm root cause in `failed_run_diagnostics.json`.
3. Use `fail_reasons.json` to validate whether issue class is systemic.
4. Use `saturation.json` and `latency_percentiles.json` to determine if contention/rate limits contributed.
5. Use `retries.json` to identify retry hotspots by tool/step.

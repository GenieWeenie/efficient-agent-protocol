# Observability

EAP provides structured logging defaults and operational metrics export.

## Structured Logging

- Default format is JSON.
- Override with:
  - `EAP_LOG_FORMAT=text` for plain text
  - `EAP_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR`
  - `EAP_LOG_JSON` (legacy boolean override)

Logs are configured through `eap.protocol.configure_logging()`.

## Metrics Snapshot Export

`StateManager` exposes:

- `collect_operational_metrics()`
- `export_operational_metrics(output_path=...)`

You can export metrics with:

```bash
python3 scripts/export_metrics.py --db-path agent_state.db --output metrics/latest.json
```

Snapshot fields include:

- pointer-store counts (total/active/expired)
- execution run and trace-event summaries
- conversation session/turn counts

This path is intended for operational diagnostics and periodic health snapshots.

## Telemetry Pack Export

For dashboard-ready diagnostics with retries, saturation, failure reasons, and latency percentiles:

```bash
python3 scripts/export_telemetry_pack.py \
  --db-path agent_state.db \
  --output-dir artifacts/telemetry
```

This writes structured artifacts plus a triage report:

- `overview.json`
- `retries.json`
- `fail_reasons.json`
- `latency_percentiles.json`
- `saturation.json`
- `failed_run_diagnostics.json`
- `operator_report.md`
- `manifest.json`

Use `failed_run_diagnostics.json` and `operator_report.md` as the first stop for root-cause analysis.

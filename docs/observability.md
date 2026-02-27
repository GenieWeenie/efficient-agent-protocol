# Observability

EAP provides structured logging defaults and operational metrics export.
The schemas below are frozen for v1 — see `docs/v1_contract.md` for the
full compatibility contract.

## Structured Logging

Default format is JSON.  Override with environment variables:

| Variable | Values | Default |
| --- | --- | --- |
| `EAP_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `EAP_LOG_FORMAT` | `json` / `text` | `json` |
| `EAP_LOG_JSON` | `1` / `true` / `yes` (legacy override) | — |

Logs are configured through `eap.protocol.configure_logging()`.

### JSON Log Schema (v1 Frozen)

When `EAP_LOG_FORMAT=json`, each line is a JSON object:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `timestamp_utc` | `string` | yes | ISO 8601 local time (`%Y-%m-%dT%H:%M:%S`) |
| `level` | `string` | yes | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `logger` | `string` | yes | Logger name (e.g. `eap`) |
| `message` | `string` | yes | Log message (post-redaction) |
| `step_id` | `string` | no | Present when log originates from a step context |
| `tool_name` | `string` | no | Present when log originates from a tool context |

No additional fields are emitted in the base JSON log format.

### Redaction

Patterns matching `api_key`, `token`, or `password` followed by `=` or `:`
are replaced with `[REDACTED]` before emission.

## Metrics Snapshot Export

`StateManager` exposes:

- `collect_operational_metrics()` — returns the metrics dict
- `export_operational_metrics(output_path=...)` — writes JSON to disk

```bash
python3 scripts/export_metrics.py --db-path agent_state.db --output metrics/latest.json
```

### Operational Metrics Schema (v1 Frozen)

```
{
  "snapshot_utc":  string (ISO 8601 with timezone),
  "db_path":       string,
  "pointer_store": {
    "total_pointers":   int,
    "active_pointers":  int,
    "expired_pointers": int
  },
  "execution": {
    "run_count":             int,
    "failed_run_count":      int,
    "total_steps":           int,
    "succeeded_steps":       int,
    "failed_steps":          int,
    "avg_duration_ms":       float,
    "trace_event_total":     int,
    "diagnostics_run_count": int,
    "trace_events_by_type":  { "<event_type>": int }
  },
  "conversation": {
    "session_count": int,
    "turn_count":    int
  }
}
```

`trace_events_by_type` keys are the `ExecutionTraceEventType` enum values:
`replayed`, `queued`, `approval_required`, `approved`, `rejected`, `started`,
`retried`, `failed`, `completed`.

## Telemetry Pack Export

For dashboard-ready diagnostics with retries, saturation, failure reasons,
and latency percentiles:

```bash
python3 scripts/export_telemetry_pack.py \
  --db-path agent_state.db \
  --output-dir artifacts/telemetry
```

### Telemetry Pack Artifacts (v1 Frozen)

| Artifact | Required top-level keys |
| --- | --- |
| `overview.json` | `generated_at_utc`, `total_runs`, `failed_runs`, `failure_rate_pct` |
| `retries.json` | `generated_at_utc`, `total_retries`, `retries_by_tool` |
| `fail_reasons.json` | `generated_at_utc`, `total_failures`, `by_error_type` |
| `latency_percentiles.json` | `generated_at_utc`, `overall`, `by_tool` |
| `saturation.json` | `generated_at_utc`, `aggregate` |
| `actors.json` | `generated_at_utc`, `actors` |
| `failed_run_diagnostics.json` | `generated_at_utc`, `runs` |
| `operator_report.md` | (Markdown — no JSON keys) |
| `manifest.json` | `generated_at_utc`, `artifacts` |

Use `failed_run_diagnostics.json` and `operator_report.md` as the first
stop for root-cause analysis.

### Execution Diagnostics Payload

`StateManager.store_execution_diagnostics(run_id, payload)` accepts a
free-form dict.  The following top-level keys are consumed by the telemetry
pipeline and are frozen:

| Key | Type | Description |
| --- | --- | --- |
| `saturation_metrics` | `dict` | Guardrail wait counts and durations |
| `approval_metrics` | `dict` | Step approval/rejection counts |
| `actor_metadata` | `dict` | Run ownership and scope information |

# Performance Tuning Guide

Recommended tuning patterns for EAP deployments under load.

## SQLite Storage

EAP uses WAL (Write-Ahead Logging) mode by default for better concurrent read/write performance. For high-throughput deployments:

- **Connection pooling**: The `StateManager` opens short-lived connections per operation. For sustained write loads, consider using the `append_trace_events_batch()` method to write multiple trace events in a single transaction.
- **PRAGMA synchronous=NORMAL**: Default setting balances durability with write speed. Only change to `FULL` if you require strict crash safety guarantees.
- **Vacuum schedule**: For long-running deployments, schedule periodic `VACUUM` on the state DB to reclaim space from deleted pointers and expired data.

## Executor Concurrency

| Environment Variable | Default | Description |
|---|---|---|
| `EAP_EXECUTOR_MAX_CONCURRENCY` | 8 | Max parallel tool executions |
| `EAP_EXECUTOR_GLOBAL_RPS` | (unset) | Global requests-per-second rate limit |
| `EAP_EXECUTOR_GLOBAL_BURST` | (unset) | Burst capacity for rate limiter |

### Per-Tool Limits

Set via `EAP_EXECUTOR_PER_TOOL_LIMITS_JSON`:

```json
{
  "scrape_url": {"max_concurrency": 2, "requests_per_second": 1.0, "burst_capacity": 3},
  "analyze_data": {"max_concurrency": 4}
}
```

## Retry / Timeout Defaults

| Parameter | Default | Tuning Guidance |
|---|---|---|
| `max_attempts` | 3 | Reduce to 1-2 for fast-fail workflows; increase for flaky external tools |
| `initial_delay_seconds` | 1.0 | Lower for local tools (0.1-0.5); higher for rate-limited APIs (2-5) |
| `backoff_multiplier` | 2.0 | Standard exponential backoff; reduce to 1.5 for tighter latency budgets |
| `timeout_seconds` | 60 | Per-provider; reduce for local models (10-30), increase for large cloud models (120+) |

## Runtime HTTP API

| Environment Variable | Default | Description |
|---|---|---|
| Rate limit (execute) | 60 req/60s | Adjust via guardrails config |
| Rate limit (read) | 240 req/60s | Higher for dashboard/polling clients |
| Concurrency (global) | 12 inflight | Scale with available CPU/memory |
| Concurrency (execute) | 6 inflight | Limit based on tool resource needs |

## Pointer Lifecycle

- Set `ttl_seconds` on pointers to enable automatic cleanup and reduce DB growth.
- Configure the pointer janitor interval via `EAP_POINTER_JANITOR_INTERVAL_SECONDS` (default: 300s).
- Limit janitor batch size via `EAP_POINTER_JANITOR_MAX_DELETE` (default: 200) to bound cleanup latency.

## Profiling Hot Paths

The primary hot paths by frequency:
1. **Trace event writing** — `StateManager.append_trace_event()` per step lifecycle event
2. **Pointer storage** — `StateManager.store_and_point()` per tool output
3. **Checkpoint upserts** — `StateManager.upsert_run_checkpoint()` per execution state change

Use `--verbose` flags on CLI scripts to observe timing. For deeper profiling, enable `EAP_LOG_LEVEL=DEBUG` to see per-operation durations in structured logs.

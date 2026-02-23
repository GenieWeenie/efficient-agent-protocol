# EAP Proof Sheet: Why Choose EAP

This is a one-page decision brief for teams evaluating EAP against general-purpose agent orchestration stacks.

## Where EAP Is Strong

- Pointer-backed state keeps large intermediate payloads out of LLM context (`ptr_*` references instead of raw payload replay).
- Dependency-aware DAG execution runs independent steps in parallel with typed retry + failure contracts.
- Built-in execution traces and run summaries make retries/failures auditable by default.
- Local-first operation with optional Redis/PostgreSQL backends for pointer storage.

## Evidence Snapshot

Source: `docs/benchmarks.md` (baseline date: 2026-02-23)

- Concurrency-limit perf path: `0.28s` (`test_global_concurrency_limit_caps_parallel_work`)
- Rate-limit saturation path: `1.70s` (`test_rate_limit_generates_saturation_metrics`)
- Distributed lease recovery paths: `0.01s` each (`test_expired_lease_is_reassigned`, `test_stale_completion_report_is_rejected_after_reassignment`)
- CI perf regression guards:
  - global-concurrency path must stay `< 2.0s`
  - rate-limit path must stay `< 4.0s`

## Failure-Mode Evidence

| Scenario | Expected behavior | Evidence |
| --- | --- | --- |
| Transient tool failure | Retry and then succeed when policy allows | `tests/integration/test_executor_retries.py` |
| Non-retryable timeout | Fail fast with typed `tool_execution_error` | `tests/integration/test_reliability_failures.py` |
| Upstream step fails | Downstream dependency marked `dependency_error` | `tests/integration/test_reliability_failures.py` |
| Retry/fail/approval/replay trace visibility | `replayed/queued/approval_required/approved/rejected/started/retried/failed/completed` persisted with run summary | `tests/integration/test_execution_traces.py`, `tests/integration/test_human_approval.py`, `tests/integration/test_resume_replay.py` |
| Pointer lifecycle cleanup | Expired pointers filtered and cleaned idempotently | `tests/integration/test_pointer_ttl.py` |
| Distributed worker lease expiry | Expired lease is reassigned; stale completion rejected | `tests/perf/test_distributed_resilience.py` |

## Quick Verification Commands

```bash
python3 -m pytest -q tests/integration/test_executor_retries.py
python3 -m pytest -q tests/integration/test_reliability_failures.py
python3 -m pytest -q tests/integration/test_execution_traces.py
python3 -m pytest -q tests/perf --durations=10
```

## Decision Rule

Choose EAP when you need predictable tool orchestration with strong failure semantics, pointer-based state management, and observable execution behavior.

Choose a broader framework if your priority is large ecosystem integrations over execution-contract rigor.

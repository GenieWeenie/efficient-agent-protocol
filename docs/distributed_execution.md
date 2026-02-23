# Distributed Execution Protocol

This document defines the coordinator-worker protocol and lease model for distributed DAG execution.

## Roles

- Coordinator:
  - Owns run state and global scheduling.
  - Assigns runnable steps to workers via leases.
  - Persists final step status (`queued`, `started`, `retried`, `failed`, `completed`).
- Worker:
  - Polls for work.
  - Claims lease for a step attempt.
  - Emits heartbeats while executing.
  - Reports completion/failure.

## Core Entities

## Lease

Lease fields:
- `lease_id`: unique lease identifier.
- `run_id`: macro run identifier.
- `step_id`: DAG step identifier.
- `worker_id`: worker that owns this lease.
- `attempt`: attempt index starting at 1.
- `issued_at_utc`
- `expires_at_utc`
- `heartbeat_at_utc`
- `status`: `active | expired | released | completed | failed`

Lease duration:
- Default lease TTL: 30s.
- Heartbeat interval: 5s.
- Lease renewal extends `expires_at_utc` by lease TTL from heartbeat time.

## Queue Item

- `run_id`
- `step_id`
- `priority`
- `queued_at_utc`
- `attempt`
- `dependency_state` summary

## Protocol Operations

## 1. Poll

Worker request:
- `worker_id`
- `capacity` (remaining slots)
- optional `tool_allowlist`

Coordinator response:
- zero or more leases with step payloads

Rules:
- Coordinator only assigns steps with satisfied dependencies.
- Coordinator enforces max-attempts and backoff schedule.

## 2. Heartbeat

Worker sends:
- `lease_id`
- `worker_id`
- `run_id`
- `step_id`
- `progress` (optional metadata)

Coordinator:
- Validates lease ownership.
- Extends lease expiry if lease still active.
- Marks lease stale if heartbeat arrives after expiry.

## 3. Complete

Worker sends:
- `lease_id`
- `output_pointer_id`
- optional `duration_ms`
- optional `metadata`

Coordinator:
- Validates active ownership.
- Marks step `completed`.
- Releases lease as `completed`.
- Unblocks downstream runnable steps.

## 4. Fail

Worker sends:
- `lease_id`
- structured `error_payload`
- optional `retry_delay_seconds`

Coordinator:
- Increments attempt count.
- If retryable and attempts remain: enqueue retry after backoff.
- Else mark step terminal `failed`, propagate downstream blocked/fallback semantics.

## Lease Expiry & Recovery

- If no heartbeat before `expires_at_utc`, coordinator marks lease `expired`.
- Expired lease step is re-queued with incremented attempt when retry policy allows.
- Coordinator deduplicates late completion/failure reports by lease status and attempt.
- Worker should stop execution when lease is known expired or ownership rejected.

## Idempotency Rules

- `complete` and `fail` are idempotent per `lease_id`.
- Duplicate terminal reports for same lease return last known terminal state.
- Coordinator rejects terminal reports for stale attempts after a new lease has been issued.

## Ordering Guarantees

- Per `(run_id, step_id)`, attempts are strictly increasing.
- At most one `active` lease exists per `(run_id, step_id, attempt)`.
- Terminal event order for a step attempt: `started -> (completed|failed)`.

## Failure Domains

- Worker crash:
  - Coordinator recovers via lease expiry.
- Coordinator restart:
  - Lease and queue state must be persisted durably.
- Network partition:
  - Heartbeat timeout triggers reassignment; stale worker completion is rejected via lease versioning.

## Security & Isolation

- Worker identity must be authenticated (`worker_id` + credentials).
- Coordinator validates worker authorization for team/run scope.
- Payloads and pointer IDs are treated as sensitive; avoid logging raw payloads.

## Metrics

- Lease acquisition latency.
- Heartbeat jitter and timeout rate.
- Reassignment count.
- Retry rate by tool/step.
- Time-to-complete per step and run.

## Compatibility with Existing EAP Models

- Distributed events map to `ExecutionTraceEvent` lifecycle.
- Final run summaries map to `execution_run_summaries`.
- Retry/backoff behavior follows `RetryPolicy`.

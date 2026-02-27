# Pointer Internals

This document explains how EAP pointer-backed state (`ptr_*`) works under the hood.

## Why Pointers Exist

EAP stores heavy tool outputs outside planner context and passes lightweight references between steps.

- Keeps prompt payloads small.
- Preserves full artifacts for replay and auditing.
- Supports crash-safe resume without recomputing completed steps.

## Pointer Record Model

Every pointer has:

- `pointer_id` (format `ptr_<8hex>`)
- `raw_data` (string payload)
- `summary` (short human-readable status)
- `metadata` (JSON object)
- lifecycle fields:
  - `created_at_utc`
  - `ttl_seconds` (optional)
  - `expires_at_utc` (optional)

`StateManager.store_and_point(...)` adds baseline metadata automatically:

- `size_bytes` (`sys.getsizeof(raw_data)`)
- `created_at_utc`
- `ttl_seconds`
- `expires_at_utc`

Executor-added metadata commonly includes:

- `execution_run_id`
- `actor_id`
- `owner_actor_id`
- step status metadata (`status`, `error_type`, branch skip reasons)

## Storage Backends

Pointer backends implement `PointerStoreBackend`:

- `initialize`
- `store_pointer`
- `retrieve_pointer`
- `list_pointers`
- `delete_pointer`

Built-in backends:

- `SQLitePointerStore` (default)
- `RedisPointerStore`
- `PostgresPointerStore`

All backends share the same lifecycle semantics (`is_expired`, `cleanup_expired_pointers`).

## Write Path

1. Executor completes a step (or emits skip/reject/error payload).
2. Executor calls `StateManager.store_and_point(...)`.
3. `StateManager` generates ID (`ptr_*`) and computes lifecycle metadata.
4. Pointer backend persists the record.
5. Executor stores only pointer response in step/run state:
   - `pointer_id`
   - `summary`
   - `metadata`

## Read Path

Step argument resolution in `AsyncLocalExecutor` supports:

- `"$step:<step_id>"` or `"$<step_id>"` dependency references.
- direct `ptr_*` references.

Resolution flow:

1. Resolve upstream pointer ID.
2. Enforce dependency status is `ok`.
3. Load payload via `StateManager.retrieve(pointer_id)`.
4. Validate resolved argument object against the tool schema.
5. Invoke tool with resolved values.

## Payload Encoding Contract

Pointer payload is stored as text (`str(raw_data)` in `StateManager`).

Implications:

- Primitive strings round-trip naturally.
- Dict/list values are stored as Python string representations unless caller serializes first.
- For structured payloads, explicitly `json.dumps(...)` before storing or return JSON text from tools.
- Consumers should parse with `json.loads(...)` only when payload is valid JSON.

## TTL And Expiry Semantics (v1 Frozen)

These semantics are frozen for v1.0 stability. See `docs/v1_contract.md` for the full contract.

- `ttl_seconds` must be a positive integer when provided; zero, negative, boolean, and float values raise `ValueError`.
- `expires_at_utc` is computed as `created_at_utc + timedelta(seconds=ttl_seconds)`.
- A pointer is expired when `expires_at_utc <= now_utc` (boundary-inclusive).
- Pointers without `ttl_seconds`/`expires_at_utc` never expire automatically.
- Expired pointers remain retrievable until explicitly deleted or cleaned up.
- `list_pointers(include_expired=True)` returns all pointers; `include_expired=False` filters expired.
- Each listed record includes an `is_expired` boolean field.
- Results are ordered by `created_at_utc DESC, pointer_id DESC`.
- `cleanup_expired_pointers(now_utc, limit)` deletes expired pointers and returns a report with `deleted_count`, `deleted_pointer_ids`, `remaining_expired_count`, `ran_at_utc`.
- Cleanup is idempotent: calling with no expired pointers returns `deleted_count=0`.
- Non-expired pointers are never deleted by cleanup.

## Checkpoints, Resume, And Replay

Pointer IDs are the replay boundary for crash-safe recovery:

- Checkpoints persist `step_status` and `pointer_id` per step.
- On resume, completed steps emit `replayed` trace events and reuse existing pointers.
- Replay does not recompute completed steps unless missing/invalid checkpoint state forces failure.

Related run persistence:

- `execution_run_checkpoints`
- `execution_trace_events`
- `execution_run_summaries`
- `execution_run_diagnostics`

## Operational Routines

Inspect pointer inventory:

```python
from eap.protocol import StateManager

state = StateManager(db_path="agent_state.db")
print(state.list_pointers(include_expired=True, limit=20))
```

Cleanup expired pointers:

```python
from eap.protocol import StateManager

state = StateManager(db_path="agent_state.db")
print(state.cleanup_expired_pointers(limit=500))
```

Fetch a specific payload:

```python
from eap.protocol import StateManager

state = StateManager(db_path="agent_state.db")
print(state.retrieve("ptr_deadbeef"))
```

## Reliability Notes

- Treat pointers as immutable references to historical run artifacts.
- Prefer explicit JSON payload contracts for inter-step data.
- Keep summaries concise; they appear in UI, traces, and runtime APIs.
- Use TTL only when data retention policy allows expiration.

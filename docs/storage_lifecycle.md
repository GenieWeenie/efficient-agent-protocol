# Pointer Storage Lifecycle

This document describes how pointer records age, expire, and are cleaned up.

> **v1 Status:** Pointer lifecycle semantics are frozen for v1.0. See `docs/v1_contract.md` for the full contract.

## Pointer lifecycle fields

Pointers in `state_store` track lifecycle metadata:
- `created_at_utc`: UTC creation timestamp.
- `ttl_seconds`: optional time-to-live in seconds.
- `expires_at_utc`: optional UTC expiration timestamp (`created_at_utc + ttl_seconds`).

When older databases are opened, `StateManager` migrates `state_store` in place by adding missing lifecycle columns and backfilling `created_at_utc`.

## Creation behavior

Use `store_and_point(..., ttl_seconds=<int>)` to create expiring pointers:
- `ttl_seconds` is optional.
- If provided, it must be a positive integer.
- If omitted, the pointer does not expire automatically.

## Lifecycle APIs

`StateManager` provides lifecycle management APIs:
- `list_pointers(include_expired=True|False, now_utc=None, limit=None)`
- `list_expired_pointers(now_utc=None, limit=None)`
- `delete_pointer(pointer_id)`
- `cleanup_expired_pointers(now_utc=None, limit=None)`

`now_utc` allows deterministic cleanup/list testing by passing a fixed ISO timestamp.

## Dashboard janitor

The Streamlit app runs a periodic janitor that deletes expired pointers.

Environment variables:
- `EAP_POINTER_JANITOR_ENABLED` (default: enabled)
- `EAP_POINTER_JANITOR_INTERVAL_SECONDS` (default: `300`)
- `EAP_POINTER_JANITOR_MAX_DELETE` (default: `200`)

The dashboard also exposes a manual "Cleanup Expired Pointers" action.

## Operational notes

- Expired pointers remain retrievable until cleanup runs.
- Cleanup is idempotent when no pointers are expired.
- Use limits on cleanup/list APIs to bound maintenance cost in large vaults.

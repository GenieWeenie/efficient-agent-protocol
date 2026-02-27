# V1 Compatibility Contract

This document defines the enforced compatibility surface that must remain stable
for `v1.0` consumers.

While the project is still `0.x`, this contract is validated by CI to prevent
accidental drift.

## Scope

The `v1.0` contract covers:

- Public Python entry-point exports in:
  - `eap.protocol`
  - `eap.environment`
  - `eap.agent`
  - `eap.runtime`
- Workflow graph schema fields and enum values for:
  - `PersistedWorkflowGraph`
  - `WorkflowGraphNode`
  - `WorkflowGraphEdge`
  - `WorkflowEdgeKind`
- Tool error payload envelope (`ToolErrorPayload`) including allowed `error_type`
  values.
- Frozen runtime settings key surface used by `load_settings()`.
- SDK HTTP operation path set for TypeScript and Go clients.

The source-of-truth lock file is:

- `docs/v1_contract_lock.json`

## Pointer Lifecycle Contract (Frozen)

The following pointer lifecycle semantics are frozen for `v1.0`:

### Creation

- `store_and_point(..., ttl_seconds=<int>)` creates a pointer with lifecycle fields.
- `ttl_seconds` must be a positive integer when provided, or `None` for no expiry.
- `ttl_seconds=0`, negative values, booleans, and floats raise `ValueError`.
- `created_at_utc` is set to current UTC (ISO 8601).
- `expires_at_utc` is computed as `created_at_utc + timedelta(seconds=ttl_seconds)`.
- Pointers without `ttl_seconds` never expire automatically.

### Expiry Evaluation

- A pointer is expired when `expires_at_utc <= now_utc` (inclusive of boundary).
- Pointers without `expires_at_utc` (or with empty/null value) are never expired.
- All UTC comparisons use timezone-aware datetimes; naive inputs are treated as UTC.

### Listing

- `list_pointers(include_expired=True)` returns all pointers including expired ones.
- `list_pointers(include_expired=False)` excludes expired pointers.
- Each returned record includes an `is_expired` boolean field.
- Results are ordered by `created_at_utc DESC, pointer_id DESC`.
- `limit` must be a positive integer when provided; `limit <= 0` raises `ValueError`.

### Retrieval

- `retrieve(pointer_id)` returns raw payload for any pointer, including expired ones.
- Expired pointers remain retrievable until explicitly deleted or cleaned up.
- Missing pointers raise `KeyError`.

### Deletion

- `delete_pointer(pointer_id)` removes a single pointer.
- Missing pointers raise `KeyError`.
- Deletion is idempotent at the backend level (backend returns `False` for missing).

### Cleanup

- `cleanup_expired_pointers(now_utc, limit)` deletes expired pointers up to `limit`.
- Returns a report: `deleted_count`, `deleted_pointer_ids`, `remaining_expired_count`, `ran_at_utc`.
- Cleanup is idempotent: calling with no expired pointers returns `deleted_count=0`.
- `remaining_expired_count` reflects the state after deletion.
- Non-expired pointers are never deleted by cleanup.

### Backend Consistency

- All backends (`SQLitePointerStore`, `RedisPointerStore`, `PostgresPointerStore`) share the same lifecycle semantics via `PointerStoreBackend` base class.
- `list_expired_pointers` and `cleanup_expired_pointers` are implemented in the base class and delegate to backend-specific `list_pointers` and `delete_pointer`.

## Deprecated Namespaces

The following legacy import paths are deprecated as of `v0.1.9` and will be
removed in `v2.0`:

| Legacy namespace | Replacement |
| --- | --- |
| `protocol` | `eap.protocol` |
| `environment` | `eap.environment` |
| `agent` | `eap.agent` |

Importing any symbol from these legacy namespaces emits a `DeprecationWarning`
with the recommended replacement.

## Unstable / Excluded Surfaces

The following are explicitly **not** part of the `v1.0` contract and may change
without a contract-lock bump:

- `eap.environment.tools` / `environment.tools` — bundled convenience tools
  and schemas.  These are starter-pack utilities; pin a specific package version
  if you depend on them.

## Non-Goals

The following remain out of scope for `v1.0` stability guarantees:

- Streamlit UI layout and UX details in `app.py`
- Internal module organization under non-`eap.*` namespaces
- Experimental plugin manifest fields not exported through `eap.environment`
- Advanced distributed coordination semantics beyond documented behavior

## Enforcement

CI enforces contract stability through:

- `scripts/check_v1_contract.py`
- `tests/contract/test_v1_contract_lock.py`
- `tests/unit/test_v1_contract_gate.py`

What fails CI:

1. Runtime surface differs from `docs/v1_contract_lock.json`.
2. Contract lock changes without an explicit package version bump.

This provides a measurable gate for compatibility changes before `v1.0`.

## Intentional Contract Changes

If you intentionally change the frozen contract surface:

1. Bump package version in `pyproject.toml`.
2. Regenerate lock:
   - `PYTHONPATH=. python scripts/check_v1_contract.py --write-lock`
3. Update this document and release notes.
4. Ensure CI passes with the new lock.

## Supported User Profile

Best fit:

- Python developers building local tool-execution agents.
- Teams that need deterministic execution traces and pointer-backed state.
- Users comfortable with explicit compatibility gates during pre-`1.0`.

Not ideal yet:

- Teams requiring long-term, SLA-backed support commitments.
- Non-technical users expecting no-code setup.
- Fully managed hosted-control-plane expectations.

## Release Notes Requirements

Every release must include, when applicable:

- `Added`
- `Changed`
- `Fixed`
- `Deprecated`
- `Removed`
- `Breaking Changes`
- `Upgrade Notes`

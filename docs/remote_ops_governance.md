# Remote Operations Governance Baseline (EAP-094)

This baseline defines minimum controls for multi-user remote runtime operation.

## Auth Scope Model

Runtime operations map to required scopes:

- `runs:execute`: `POST /v1/eap/macro/execute`
- `runs:resume`: `POST /v1/eap/runs/{run_id}/resume`
- `runs:read`: `GET /v1/eap/runs/{run_id}`
- `pointers:read`: `GET /v1/eap/pointers/{pointer_id}/summary`

Cross-run elevated scopes:

- `runs:resume:any`: resume runs owned by other actors
- `runs:read:any`: inspect runs owned by other actors
- `pointers:read:any`: inspect pointers owned by other actors

## Ownership And Access Boundaries

- Every run records actor metadata (`owner_actor_id`, current `actor_id`, `actor_scopes`, `operation`).
- Run ownership is established on execute and persisted in checkpoints/diagnostics.
- By default, actors can only read/resume their own runs.
- `*:any` scopes are required for cross-run access.

Pointer summary access boundaries:

- If pointer metadata includes `execution_run_id`, pointer reads are evaluated against run ownership rules.
- Unscoped pointer reads across owners are denied.

## Audit Logging Expectations

Minimum operator log/audit fields to capture at ingress/proxy or service boundary:

- actor identity (`actor_id` or mapped auth subject)
- endpoint + HTTP method
- authorization result (allowed/denied)
- run ID and pointer ID (when present)
- timestamp and source IP

EAP runtime trace and diagnostics include actor metadata for run-affecting operations.

## Retention Baseline

Recommended defaults (tune per compliance needs):

- `execution_trace_events`: 30-90 days
- `execution_run_summaries`: 90-180 days
- `execution_run_diagnostics`: 30-90 days
- pointer payloads: policy-driven; ensure TTL and cleanup for sensitive data

Operational controls:

- periodic backup of runtime state volume
- periodic pointer TTL cleanup
- access review for scoped tokens and elevated (`*:any`) scopes

## Rate Limits And Concurrency Guards (EAP-096)

Runtime now enforces request throttling guardrails with deterministic `429` responses.

Defaults:

- Rate limits (per actor, per operation, 60-second window):
  - `macro_execute`: 60 requests
  - `run_resume`: 60 requests
  - `run_read`: 240 requests
  - `pointer_summary`: 240 requests
- Concurrency:
  - `global_inflight`: 12
  - `execute_inflight`: 6
  - `resume_inflight`: 6
  - `per_run_resume_inflight`: 1

Response semantics:

- `error_type=rate_limited` with `Retry-After` header when rate windows are exceeded.
- `error_type=throttled` when concurrency ceilings are exceeded.

Guardrail telemetry:

- runtime emits structured guardrail events to service logs with prefix:
  - `[runtime:guardrail]`
- event payload includes `event_type`, limit details, cumulative counters, and timestamp.

Optional guardrails config (`--guardrails-config`):

```json
{
  "rate_limits": {
    "macro_execute": {"max_requests": 60, "window_seconds": 60},
    "run_resume": {"max_requests": 60, "window_seconds": 60},
    "run_read": {"max_requests": 240, "window_seconds": 60},
    "pointer_summary": {"max_requests": 240, "window_seconds": 60}
  },
  "concurrency": {
    "global_inflight": 12,
    "execute_inflight": 6,
    "resume_inflight": 6,
    "per_run_resume_inflight": 1
  }
}
```

## Scoped Token Config Example

`scripts/eap_runtime_service.py` accepts `--scoped-auth-config` with this schema:

```json
{
  "tokens": [
    {
      "token": "token-ops-read",
      "actor_id": "ops-reader",
      "scopes": ["runs:read", "pointers:read", "runs:read:any", "pointers:read:any"]
    },
    {
      "token": "token-ops-write",
      "actor_id": "ops-writer",
      "scopes": ["runs:execute", "runs:resume", "runs:read", "pointers:read"]
    }
  ]
}
```

## Policy Profiles And Templates (EAP-095)

Runtime scoped auth now supports built-in policy profiles with template-based grants.

Default profile: `strict` (deny-by-default for any scope not granted by template/explicit config).

Profiles:

- `strict`
  - `viewer`: `runs:read`, `pointers:read`
  - `operator`: `runs:execute`, `runs:resume`, `runs:read`, `pointers:read`
  - `auditor`: `runs:read`, `pointers:read`, `runs:read:any`, `pointers:read:any`
  - `admin`: `runs:read`, `pointers:read`, `runs:read:any`, `pointers:read:any`
- `balanced`
  - same templates as `strict`, but `admin` also gets resume-any (`runs:resume:any`)
- `trusted`
  - same templates as `strict`, but `admin` maps to `*` (full runtime scope)

Policy-profile config format:

```json
{
  "policy_profile": "strict",
  "tokens": [
    {
      "token": "token-viewer",
      "actor_id": "ops-viewer",
      "template": "viewer"
    },
    {
      "token": "token-operator",
      "actor_id": "ops-operator",
      "template": "operator"
    }
  ]
}
```

Per-token overrides:

- optional `policy_profile` to override the file default for one token
- optional explicit `scopes` list to add permitted scopes for that token
- scopes disallowed by selected profile are rejected at startup
- tokens resolving to zero scopes are rejected (deny-by-default)

Run with scoped config:

```bash
python scripts/eap_runtime_service.py \
  --host 0.0.0.0 \
  --port 8080 \
  --db-path /var/lib/eap/agent_state.db \
  --policy-profile strict \
  --guardrails-config /etc/eap/guardrails.json \
  --scoped-auth-config /etc/eap/scoped_auth.json
```

You may keep `--bearer-token` as an emergency admin token with full runtime scopes.

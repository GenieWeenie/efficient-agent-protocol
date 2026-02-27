# Typing Policy

This document defines EAP's incremental static typing enforcement plan.

## EAP-104 Scoped Strictness Baseline

Extended in `EAP-109` to include executor runtime path, and in `EAP-110` to include runtime HTTP API typing hardening.

Current strict-typed target modules (required in CI):

- `environment.safe_eval`
- `environment.executor`
- `eap.runtime.auth_scopes`
- `eap.runtime.guardrails`
- `eap.runtime.http_api`

CI gate:

- Workflow: `.github/workflows/ci.yml`
- Step: `Type rigor gate (mypy scoped modules)` under required `Lint/Test (py3.11)`
- Command:
  - `mypy --follow-imports=skip environment/safe_eval.py environment/executor.py eap/runtime/auth_scopes.py eap/runtime/guardrails.py eap/runtime/http_api.py`

`--follow-imports=skip` keeps enforcement bounded to the scoped modules so legacy typing debt in non-scoped imports does not block this tranche.

Strictness profile:

- `strict = true`
- `disallow_any_explicit = true`

Configured in:

- `pyproject.toml` (`[tool.mypy]` + scoped overrides)

## Residual Exclusions (Explicit And Time-Bounded)

No runtime-critical modules remain outside the current strict scope. All planned tranches are complete.

| Module | Status | Completed In |
| --- | --- | --- |
| `eap/runtime/http_api.py` | Strict typing enforced | `EAP-110` |

## Rules For New Scope Additions

When adding a module to strict scope:

1. Add it to scoped mypy command in CI.
2. Add it to `pyproject.toml` strict override list.
3. Remove broad `Any` usage or document a narrowly-scoped justification.
4. Keep exclusion table updated with explicit next target/date.

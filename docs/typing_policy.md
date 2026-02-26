# Typing Policy

This document defines EAP's incremental static typing enforcement plan.

## EAP-104 Scoped Strictness Baseline

Current strict-typed target modules (required in CI):

- `environment.safe_eval`
- `eap.runtime.auth_scopes`
- `eap.runtime.guardrails`

CI gate:

- Workflow: `.github/workflows/ci.yml`
- Step: `Type rigor gate (mypy scoped modules)` under required `Lint/Test (py3.11)`
- Command:
  - `mypy --follow-imports=skip environment/safe_eval.py eap/runtime/auth_scopes.py eap/runtime/guardrails.py`

`--follow-imports=skip` keeps enforcement bounded to the scoped modules so legacy typing debt in non-scoped imports does not block this tranche.

Strictness profile:

- `strict = true`
- `disallow_any_explicit = true`

Configured in:

- `pyproject.toml` (`[tool.mypy]` + scoped overrides)

## Residual Exclusions (Explicit And Time-Bounded)

The following runtime-critical modules remain outside the EAP-104 scope and are tracked for follow-up tranches.

| Module | Reason Not In EAP-104 Scope | Target Tranche | Target Date |
| --- | --- | --- | --- |
| `environment/executor.py` | Large dynamic data-shaping surface (`ptr_*` resolution, branching context, retry metadata) needs staged annotation pass. | `EAP-109` | 2026-04-30 |
| `eap/runtime/http_api.py` | High-volume JSON/request parsing path requires typed boundary adapters before strict mode. | `EAP-110` | 2026-05-15 |

These dates are planning commitments and should be updated if tranche ordering changes.

## Rules For New Scope Additions

When adding a module to strict scope:

1. Add it to scoped mypy command in CI.
2. Add it to `pyproject.toml` strict override list.
3. Remove broad `Any` usage or document a narrowly-scoped justification.
4. Keep exclusion table updated with explicit next target/date.

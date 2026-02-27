# Phase 11 Typing Rigor Completion Roadmap

Status: In Progress  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`

Current status:
- [x] `EAP-109` strict typing tranche for executor runtime path (`GEN-65`)
- [ ] `EAP-110` strict typing tranche for runtime HTTP API path (`GEN-66`)

## Objective

Complete strict static typing coverage for remaining runtime-critical modules that were explicitly deferred by `EAP-104`.

## Ordered Implementation Items

| Order | EAP ID | Linear | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | `EAP-109` | `GEN-65` | Executor runtime path | Strict typing hardening for `environment/executor.py` plus CI scope update | Scoped mypy gate includes executor; focused runtime integration tests pass; typing policy/queue docs updated |
| 2 | `EAP-110` | `GEN-66` | Runtime HTTP API boundary path | Typed request/response boundary adapters in `eap/runtime/http_api.py` and CI scope update | Scoped mypy gate includes runtime HTTP API module; runtime HTTP API integration tests pass; residual exclusion table cleared/updated |

## Dependency Order

1. `EAP-109` unblocks `EAP-110` (reuse strict typing patterns and helper conventions from executor tranche).

## Execution Constraint

Only the first non-blocked `Todo` item in `docs/execution_protocol.md` may be started.

# Phase 12 V1 Launch Readiness Roadmap

Status: In Progress  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`

Current status:
- [x] `EAP-110` strict typing tranche for runtime HTTP API (`GEN-66`)
- [x] `EAP-111` freeze pointer lifecycle semantics (`GEN-67`)
- [x] `EAP-112` public API deprecation sweep + unstable export cleanup (`GEN-68`)
- [x] `EAP-113` upgrade migration verification from latest `0.x` baseline (`GEN-69`)
- [x] `EAP-114` observability compatibility lock (`GEN-70`)
- [x] `EAP-115` v1 readiness gatepack (`GEN-71`)
- [x] `EAP-116` README/docs v1 alignment pass (`GEN-72`)
- [ ] `EAP-117` release + maintainer runbook v1 finalization (`GEN-73`)
- [ ] `EAP-118` v1 upgrade handoff artifact + RC dry-run (`GEN-74`)

## Objective

Close remaining v1 stabilization and operator-readiness gaps using an explicit, Linear-tracked, ordered queue before starting v1 cut work.

## Ordered Implementation Items

| Order | EAP ID | Linear | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | `EAP-110` | `GEN-66` | Strict typing of runtime HTTP API boundary path | Typed request/response boundary adapters in `eap/runtime/http_api.py`; CI scope update | Scoped strict mypy passes with `eap/runtime/http_api.py`; runtime HTTP API integration tests pass |
| 2 | `EAP-111` | `GEN-67` | Pointer lifecycle semantics freeze | v1-stable TTL/expiry/cleanup contract + tests | Pointer lifecycle semantics documented and contract-tested; no pointer regression |
| 3 | `EAP-112` | `GEN-68` | Public API surface stabilization | Deprecate/remove unstable exports with upgrade guidance | No undocumented unstable exports remain; contract/tests green |
| 4 | `EAP-113` | `GEN-69` | Upgrade migration verification | Deterministic migration/rollback validation from v0.1.8 baseline fixtures | Migration + rollback flow succeeds with docs + commands |
| 5 | `EAP-114` | `GEN-70` | Observability compatibility lock | Log/metrics/telemetry compatibility contract + checks | Key observability schemas/fields documented and tested |
| 6 | `EAP-115` | `GEN-71` | V1 readiness gatepack | Unified required gate execution path with artifact mapping | One runbook/command path validates required v1 gates |
| 7 | `EAP-116` | `GEN-72` | README/docs v1 alignment | Quickstart/docs link + claims alignment pass | Public docs reflect shipped reality; claim checks green |
| 8 | `EAP-117` | `GEN-73` | Runbook finalization + sign-off | Final release/maintainer runbooks with owner sign-off criteria | Runbooks are v1-ready and internally consistent |
| 9 | `EAP-118` | `GEN-74` | V1 upgrade handoff + RC dry-run | Final upgrade handoff artifact + RC dry-run evidence | Decision-ready go/no-go checklist complete |

## Dependency Order

1. `EAP-110` first (typing boundary hardening unblocks higher-level API stabilization confidence).
2. `EAP-111` and `EAP-112` next to freeze data/API contracts.
3. `EAP-113` and `EAP-114` then validate operational compatibility.
4. `EAP-115` aggregates gates after prior contract work is in place.
5. `EAP-116` and `EAP-117` finalize user/operator docs and runbooks.
6. `EAP-118` is final pre-v1 dry-run and handoff.

## Execution Constraint

Do not start implementation until user confirms queue order and scope.

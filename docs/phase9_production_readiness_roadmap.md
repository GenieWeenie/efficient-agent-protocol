# Phase 9 Production Readiness Roadmap

Status: In progress (started 2026-02-24)  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`

Current status:
- [x] `EAP-095` runtime policy profile packs + deny-by-default templates (`GEN-55`)
- [x] `EAP-096` runtime rate limits and concurrency guards (`GEN-56`)
- [x] `EAP-097` audit log export + signed integrity manifest (`GEN-57`)
- [x] `EAP-098` backup/restore workflow for state + diagnostics (`GEN-58`)
- [ ] `EAP-099` long-run soak + chaos reliability gate (`GEN-59`)

## Objective

Move from feature-complete Phase 8 to production-readiness controls that improve safe multi-team operation and operational trust.

## Gap-to-Workstream Mapping

| Gap | Phase 9 Workstream |
| --- | --- |
| Need safer default policy posture for remote operation | `EAP-095` |
| Risk of noisy-neighbor behavior under shared runtime load | `EAP-096` |
| Need stronger, portable audit evidence | `EAP-097` |
| Need operator runbooks for recovery events | `EAP-098` |
| Need hard reliability proof under stress conditions | `EAP-099` |

## Ordered Implementation Items

| Order | EAP ID | Linear | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | `EAP-095` | `GEN-55` | Runtime policy profile packs | Built-in policy profiles (`strict`, `balanced`, `trusted`) with deny-by-default template support | Profile docs published; default profile enforced; integration tests confirm denied operations for disallowed scopes |
| 2 | `EAP-096` | `GEN-56` | Runtime rate and concurrency guards | Endpoint-level request rate limit + per-run concurrency ceilings | Runtime returns deterministic throttling responses; concurrency tests validate boundary behavior |
| 3 | `EAP-097` | `GEN-57` | Audit export integrity | Export command emits audit bundle plus signed/hashed manifest | Verification command confirms bundle integrity; tamper test fails verification as expected |
| 4 | `EAP-098` | `GEN-58` | Backup/restore operations | Operator command set for backup and restore of run state + diagnostics | Restore drills succeed in CI fixture; docs include RPO/RTO guidance and failure handling |
| 5 | `EAP-099` | `GEN-59` | Soak and chaos gate | 24-hour soak + fault-injection lane and scorecard | CI artifact includes soak/chaos summary; release gate fails on configured reliability regressions |

## Dependency Order

1. `EAP-095` unblocks `EAP-096`.
2. `EAP-096` unblocks `EAP-097`.
3. `EAP-097` unblocks `EAP-098`.
4. `EAP-098` unblocks `EAP-099`.

## Execution Constraint

`EAP-098` is complete. Global queue now advances to `EAP-099` as the active reliability gate item.

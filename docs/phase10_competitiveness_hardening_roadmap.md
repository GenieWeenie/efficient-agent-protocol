# Phase 10 Competitiveness Hardening Roadmap

Status: Queued (inserted after `EAP-097` in `docs/execution_protocol.md`)  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`

Current status:
- [x] `EAP-100` reproducible benchmark + competitor comparison suite (`GEN-60`)
- [ ] `EAP-101` docs deepening for custom tools, pointer internals, architecture completeness (`GEN-61`)
- [ ] `EAP-102` security hardening for expression-evaluation paths (`GEN-62`)
- [ ] `EAP-103` README conversion pack (demo GIF, architecture prominence, badges hygiene) (`GEN-63`)
- [ ] `EAP-104` type rigor tranche (mypy scope + stricter CI typing checks) (`GEN-64`)

## Objective

Convert external "strong but early" feedback into measurable competitiveness upgrades without weakening reliability guarantees.

## Criticism-to-Workstream Mapping

| Feedback Gap | Phase 10 Workstream |
| --- | --- |
| No reproducible side-by-side evidence vs alternatives | `EAP-100` |
| Docs depth is uneven for advanced adopters | `EAP-101` |
| Expression-eval paths need explicit hardening posture | `EAP-102` |
| README top section can convert better for first-time visitors | `EAP-103` |
| Type rigor can be raised for production confidence | `EAP-104` |

## Ordered Implementation Items

| Order | EAP ID | Linear | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | `EAP-100` | `GEN-60` | Reproducible benchmark + comparison suite | Benchmark harness and comparison table with pinned commands and dataset fixtures | CI publishes benchmark artifact; docs include exact rerun command; regression threshold gate is enforced |
| 2 | `EAP-101` | `GEN-61` | Docs depth and architecture completeness | New docs for custom tool authoring + pointer internals; architecture flow pass with complete sections | New docs linked from README and docs index; architecture doc has no TODO/cutoff gaps; quickstart path references new docs |
| 3 | `EAP-102` | `GEN-62` | Security hardening for expression-evaluation paths | Constrained evaluator path plus explicit security guidance and tests | Unsafe expressions are rejected by tests; docs describe threat model + mitigations; security scan/docs checks remain green |
| 4 | `EAP-103` | `GEN-63` | README conversion pack | Short demo GIF, prominent architecture diagram placement, badge cleanup/alignment | README top section renders correctly on GitHub; assets are lightweight and committed; smoke check validates links/assets |
| 5 | `EAP-104` | `GEN-64` | Type rigor tranche | Incremental mypy target with strictness rules on critical runtime modules | CI typing job required; target module set passes with no `Any` regressions; docs explain typing policy |

## Dependency Order

1. `EAP-097` unblocks `EAP-100`.
2. `EAP-100` unblocks `EAP-101`.
3. `EAP-101` unblocks `EAP-102`.
4. `EAP-102` unblocks `EAP-103`.
5. `EAP-103` unblocks `EAP-104`.
6. `EAP-104` unblocks deferred production-readiness items (`EAP-098`, `EAP-099`) in the global execution queue.

## Execution Constraint

Only the first non-blocked `Todo` item in `docs/execution_protocol.md` may be started (currently `EAP-101`).

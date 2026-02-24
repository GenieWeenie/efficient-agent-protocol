# Phase 8 Adoption + Limits Closure Roadmap

Status: In progress (started 2026-02-24)  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`

Current status:
- [x] `EAP-089` Responses streaming parity (`GEN-49`)
- [x] `EAP-090` v1 compatibility enforcement (`GEN-50`)
- [x] `EAP-091` one-command bootstrap (`GEN-51`)
- [ ] `EAP-092` guided onboarding + doctor (`GEN-52`)
- [ ] `EAP-093` self-hosted control-plane reference (`GEN-53`)
- [ ] `EAP-094` remote operations governance baseline (`GEN-54`)

## Objective

Turn README caveats (`Not ideal yet` and `Current limits`) into concrete deliverables that improve adoption without weakening reliability guarantees.

## Gap-to-Workstream Mapping

| README Gap | Phase 8 Workstream |
| --- | --- |
| `responses` mode lacks streaming parity | `EAP-089` |
| Pre-`1.0` contract uncertainty | `EAP-090` |
| High setup friction for first-time users | `EAP-091`, `EAP-092` |
| Teams wanting more than local-only runtime operation | `EAP-093`, `EAP-094` |

## Ordered Implementation Items

| Order | EAP ID | Linear | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | `EAP-089` | `GEN-49` | Responses streaming parity | Stream support in `responses` mode | Integration coverage for responses streaming; no chat-completions regressions; docs updated |
| 2 | `EAP-090` | `GEN-50` | v1 compatibility enforcement | Frozen v1 surfaces + CI compatibility gate | Contract docs finalized; compatibility tests required in CI; breaking-change simulation test included |
| 3 | `EAP-091` | `GEN-51` | One-command bootstrap | Bootstrap script for first successful run | Idempotent bootstrap path for macOS/Linux; actionable failure output; README quickstart updated |
| 4 | `EAP-092` | `GEN-52` | Guided onboarding + doctor | Config wizard + `doctor` validation command | Non-zero categorized failures; runnable `.env` generation; troubleshooting mapping documented |
| 5 | `EAP-093` | `GEN-53` | Self-hosted control-plane reference | Docker Compose reference deployment + ops docs | One-command stack startup; remote `/v1/eap/*` smoke check; auth/TLS guidance published |
| 6 | `EAP-094` | `GEN-54` | Remote operations governance baseline | Scoped auth + run actor metadata + governance docs | Unauthorized operations blocked by scope tests; traces include actor metadata; governance/migration docs published |

## Dependency Order

1. `EAP-089` unblocks `EAP-090`.
2. `EAP-090` unblocks `EAP-091`.
3. `EAP-091` unblocks `EAP-092`.
4. `EAP-092` unblocks `EAP-093`.
5. `EAP-093` unblocks `EAP-094`.

## Execution Constraint

Only the first non-blocked `Todo` item may be started (currently `EAP-092`).

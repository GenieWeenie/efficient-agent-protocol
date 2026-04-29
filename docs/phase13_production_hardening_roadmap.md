# Phase 13 Production Hardening Roadmap

Status: Active  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`  
Intake source: production-hardening review received 2026-04-28

Current status:
- [x] `EAP-119` production hardening intake and v1.0.1 blocker plan (`GEN-199`)
- [x] `EAP-120` collapse duplicate package trees and define canonical imports (`GEN-200`)
- [x] `EAP-121` add import and package compatibility migration tests (`GEN-201`)
- [x] `EAP-122` replace runtime HTTP server with production ASGI path (`GEN-202`)
- [x] `EAP-123` fail-closed runtime auth defaults (`GEN-203`)
- [ ] `EAP-124` sandbox local file tools (`GEN-204`)
- [ ] `EAP-125` add SSRF protection and streaming byte caps to web tools (`GEN-205`)
- [ ] `EAP-126` add macro cycle detection and execution timeout controls (`GEN-206`)
- [ ] `EAP-127` harden connection pooling and request lifecycle (`GEN-207`)
- [ ] `EAP-128` add production-hardening regression gatepack (`GEN-208`)

## Objective

Close the production blockers identified after the v1.0.0 baseline before strengthening production-readiness claims or cutting the next patch release.

This phase is intentionally blocker-first. It prioritizes correctness, security posture, and operational safety over new ecosystem features.

## Scope

The Phase 13 queue targets the confirmed P0/P1 risks from the production-hardening brief:

- duplicate package trees and ambiguous import/runtime ownership
- runtime HTTP server architecture and per-request event-loop creation
- fail-open anonymous trusted runtime auth defaults
- unrestricted local filesystem tool access
- SSRF exposure and post-load response size limiting in web tools
- macro cycle/hang risk and missing total execution timeout controls
- missing durable regression gates for these production-risk classes

## Ordered Implementation Items

| Order | EAP ID | Linear | Priority | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `EAP-119` | `GEN-199` | P0 | Intake and tracker | Create this roadmap, update `ROADMAP.md` and `docs/execution_protocol.md`, and create Linear issues for the ordered queue | Roadmap and Linear are aligned; no implementation starts before the queue is visible |
| 2 | `EAP-120` | `GEN-200` | P0 | Package ownership | Collapse duplicate runtime package trees and define `eap.*` as canonical | Fresh install exposes the intended import surface; duplicate runtime implementations are not packaged |
| 3 | `EAP-121` | `GEN-201` | P0 | Package regression tests | Add installed-package import and duplicate-tree detection tests | CI catches duplicate package regressions and docs/examples use canonical imports |
| 4 | `EAP-122` | `GEN-202` | P0 | Runtime HTTP server | Replace `ThreadingHTTPServer` / per-request `asyncio.run()` path with production ASGI path | Runtime endpoint contract tests pass through ASGI; production launch docs updated |
| 5 | `EAP-123` | `GEN-203` | P0 | Runtime auth | Make runtime auth fail closed unless explicit local-dev mode is selected | Unauthenticated requests are denied by default; dev escape hatch is explicit and documented |
| 6 | `EAP-124` | `GEN-204` | P0 | File tools | Add configurable filesystem sandbox with traversal and symlink escape protection | Read/write/list tests reject path escapes while allowed in-root operations still work |
| 7 | `EAP-125` | `GEN-205` | P0 | Web tools | Add DNS-aware SSRF protection and stream-enforced byte caps | Private/loopback/redirect SSRF cases are blocked; large responses stop at configured cap |
| 8 | `EAP-126` | `GEN-206` | P0 | Macro execution safety | Add cycle detection and total macro execution timeout controls | Direct/indirect cycles and timeout cases fail deterministically with structured errors |
| 9 | `EAP-127` | `GEN-207` | P1 | Network lifecycle | Harden connection pooling, timeout, and retry lifecycle for critical paths | Critical network paths use bounded clients or justified one-shot calls; docs cover tuning |
| 10 | `EAP-128` | `GEN-208` | P1 | Release gates | Add production-hardening regression gatepack to CI/readiness docs | CI/release gates cover all Phase 13 P0 classes with documented local command |

## Dependency Order

1. `EAP-119` must complete first so the work is visible and tracked.
2. `EAP-120` and `EAP-121` come before deeper runtime work to remove package/import ambiguity.
3. `EAP-122` and `EAP-123` harden the remote runtime boundary.
4. `EAP-124`, `EAP-125`, and `EAP-126` harden exposed tool and macro execution surfaces.
5. `EAP-127` follows the core P0s as the first P1 reliability tranche.
6. `EAP-128` closes the phase by making the fixes durable through CI/release gates.

## Execution Constraint

Do not start implementation until the ordered queue is confirmed in Linear and mirrored in `docs/execution_protocol.md`.

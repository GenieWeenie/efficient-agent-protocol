# Phase 14 Release Maintenance Roadmap

Status: Active  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`  
Intake source: post-Phase 13 completion and post-merge CI annotations from 2026-04-29

Current status:
- [x] `EAP-129` create Phase 14 release maintenance queue (`GEN-209`)
- [ ] `EAP-130` clean up package license metadata (`GEN-210`)
- [ ] `EAP-131` resolve GitHub Actions Node runtime warnings (`GEN-211`)
- [ ] `EAP-132` refresh release evidence and docs index (`GEN-212`)
- [ ] `EAP-133` run v1.0.1 release readiness dry-run (`GEN-213`)

## Objective

Close the remaining release-maintenance friction after Phase 13 so the next patch release can be cut from a clean, explainable, and fully evidenced baseline.

This phase is intentionally small. It does not add product features. It removes release noise, updates public release evidence, and verifies that `v1.0.1` is ready to tag.

## Scope

The Phase 14 queue targets the visible post-hardening maintenance items:

- non-blocking setuptools license metadata deprecation warning during package build
- GitHub Actions Node.js runtime deprecation annotations on CI jobs
- docs index drift after Phase 13 completion
- final release evidence for the current `1.0.1` package baseline

## Ordered Implementation Items

| Order | EAP ID | Linear | Priority | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `EAP-129` | `GEN-209` | P2 | Intake and tracker | Create this roadmap, update `ROADMAP.md` and `docs/execution_protocol.md`, and create Linear issues for Phase 14 | Phase 14 queue is visible in docs and Linear; first executable Todo is clear |
| 2 | `EAP-130` | `GEN-210` | P2 | Packaging metadata | Replace deprecated license metadata with current supported packaging format | Package build completes without the setuptools license metadata deprecation warning; MIT license metadata remains correct |
| 3 | `EAP-131` | `GEN-211` | P2 | CI runtime warnings | Inventory and resolve GitHub Actions Node.js runtime deprecation annotations | CI no longer emits actionable Node.js 20 warnings, or each remaining warning has a documented upstream blocker |
| 4 | `EAP-132` | `GEN-212` | P2 | Docs and release evidence | Refresh docs index, roadmap status, and v1.0.1 release evidence | Public docs show Phase 13 complete, Phase 14 active, and current release blockers/evidence accurately |
| 5 | `EAP-133` | `GEN-213` | P2 | Release dry-run | Run final v1.0.1 readiness evidence pass | Unified gatepack, package smoke, and GitHub main workflows are green or blockers are explicitly listed |

## Dependency Order

1. `EAP-129` must complete first so the new work is visible and tracked.
2. `EAP-130` removes package-build warning noise before the release dry-run.
3. `EAP-131` removes or documents CI warning noise before release evidence is refreshed.
4. `EAP-132` updates public docs and release evidence after the warning cleanup work.
5. `EAP-133` closes the phase with a go/no-go dry-run for the `v1.0.1` release.

## Execution Constraint

Do not start implementation until this ordered queue is mirrored in Linear and `docs/execution_protocol.md`. After `EAP-129` is merged, `EAP-130` is the first executable `Todo`.

# Roadmap

This roadmap tracks what is needed to recommend EAP without caveats.

## Phase 1: Product Contract (Now)

- Define `v1.0` scope and non-goals.
- Lock stability policy and versioning guarantees.
- Publish supported-user profile (who this is for / not for).

## Phase 2: Reliability and Validation

- Add contract tests for public API and workflow schema.
- Add coverage gates (line + branch) in CI.
- Add reliability tests for retries, timeouts, dependency failure, and backend outages.
- Publish reproducible performance benchmarks with regression thresholds.

## Phase 3: Release and Security Hardening

- Automate versioning/changelog workflow.
- Add release runbook with rollback steps.
- Add `SECURITY.md` and coordinated disclosure policy.
- Enable dependency/code scanning in CI.
- Add secret scanning and pre-commit checks.

## Phase 4: Operational Maturity

- Add migration policy and migration scripts for schema/state changes.
- Add observability defaults (structured logs and metrics export).
- Add contributor governance docs (`CONTRIBUTING.md`, issue/PR templates, maintainer expectations).
- Reduce bus factor with maintainer runbooks and reviewer coverage.

## Phase 5: Recommendation Readiness (Completed)

- Close all open high-severity code scanning alerts and keep the baseline at zero.
- Add maintainer/reviewer ownership map (`CODEOWNERS`) for critical runtime paths.
- Add README quickstart smoke validation in CI so onboarding docs stay executable.
- Publish a one-page "why EAP vs alternatives" proof sheet with benchmark + failure-mode evidence.
- Checklist: `docs/phase5_recommendation_readiness_checklist.md`
- Proof sheet: `docs/eap_proof_sheet.md`

## Phase 6: Distribution and V1 Readiness (In Progress)

- Publish stable package releases to PyPI from tag workflow (Trusted Publishing).
- Add post-release install smoke validation against published package artifacts.
- Finalize `v1.0` stabilization checklist and upgrade notes for external adopters.

## Phase 7: Competitive Positioning + OpenClaw Interop (Next)

- Execute OpenClaw integration track (plugin + skills + CI interop lane).
- Close remaining high-impact competitive gaps after HITL checkpoints, crash-safe resume, and MCP interop.
- Publish updated competitive proof artifacts with reproducible evidence.
- Checklist: `docs/phase7_competitive_openclaw_roadmap.md`

## Done

- Branch protection on `main` with required CI checks and PR review.
- MIT license added.
- Release workflow stabilized and validated on tagged release runs.
- Phase 1 contract draft published (`docs/v1_contract.md`).
- Release notes template published (`docs/release_notes_template.md`).
- Phase 2 reliability/contract/perf tranche completed (issue #2).
- Phase 3 release and security hardening shipped (issue #3).
- Phase 4 migration/observability/governance tranche completed (issue #4).
- Phase 5 recommendation readiness completed (`EAP-064` to `EAP-067`).
- `v0.1.4` release published with Phase 5 and CodeQL v4 updates.
- Phase 7 interop foundation started with `EAP-071` (interop matrix), `EAP-072` (runtime HTTP endpoints), and `EAP-073` (OpenClaw plugin adapter MVP).
- Phase 7 `EAP-074` skill pack added (`run`, `inspect`, `retry failed step`, `export trace`) with 5-minute quickstart.
- Phase 7 `EAP-075` interop CI lane added with pinned OpenClaw version smoke tests.
- Phase 7 `EAP-076` HITL checkpoints added (step-level pause/approve/reject semantics with trace transitions).
- Phase 7 `EAP-077` crash-safe resume/replay added with persisted run checkpoints and resume endpoint.
- Phase 7 `EAP-078` MCP interoperability added via `invoke_mcp_tool` stdio bridge and runtime integration test.
- Phase 7 `EAP-079` evaluation harness shipped with CI scorecard artifacts and regression threshold gate.
- Phase 7 `EAP-080` vertical starter packs added with runnable walkthroughs and smoke tests.
- Phase 7 `EAP-081` operator telemetry pack added with dashboard-ready diagnostics and failed-run triage artifacts.
- Phase 7 `EAP-082` competitive proof sheet refreshed with side-by-side capability matrix and reproducible validation commands.

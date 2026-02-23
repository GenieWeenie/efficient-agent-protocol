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

## Phase 5: Recommendation Readiness (Next)

- Close all open high-severity code scanning alerts and keep the baseline at zero.
- Add maintainer/reviewer ownership map (`CODEOWNERS`) for critical runtime paths.
- Add README quickstart smoke validation in CI so onboarding docs stay executable.
- Publish a one-page "why EAP vs alternatives" proof sheet with benchmark + failure-mode evidence.
- Checklist: `docs/phase5_recommendation_readiness_checklist.md`
- Proof sheet: `docs/eap_proof_sheet.md`

## Done

- Branch protection on `main` with required CI checks and PR review.
- MIT license added.
- Release workflow stabilized and validated on tagged release runs.
- Phase 1 contract draft published (`docs/v1_contract.md`).
- Release notes template published (`docs/release_notes_template.md`).
- Phase 2 reliability/contract/perf tranche completed (issue #2).
- Phase 3 release and security hardening shipped (issue #3).
- Phase 4 migration/observability/governance tranche completed (issue #4).
- Phase 5 tranche 1 started: compiler ReDoS hardening and regression tests (EAP-064).
- Phase 5 tranche 2 completed: proof sheet with benchmark and failure-mode evidence.

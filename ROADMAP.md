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

## Done

- Branch protection on `main` with required CI checks and PR review.
- MIT license added.
- Release workflow stabilized and validated on tagged release runs.
- Phase 1 contract draft published (`docs/v1_contract.md`).
- Release notes template published (`docs/release_notes_template.md`).

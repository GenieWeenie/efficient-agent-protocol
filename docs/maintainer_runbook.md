# Maintainer Runbook

This runbook captures core maintainer operations to reduce bus factor.

## Daily / Routine

- Review open issues and PRs.
- Confirm CI, Security, and CodeQL workflows are healthy.
- Triage flaky test reports and release blockers.

## Triage Process

1. Confirm reproduction details.
2. Classify severity and scope.
3. Label issue (`bug`, `enhancement`, roadmap phase labels).
4. Link issue to a milestone/roadmap task.

## Incident Response

1. Acknowledge issue and post impact statement.
2. Reproduce and isolate root cause.
3. Land fix behind CI validation.
4. Publish release and post remediation note.

## Recovery Drills

- Run periodic state backup/restore drills using `docs/state_backup_restore.md`.
- Verify integrity checks and rollback path behavior at least once per release cycle.
- Capture drill timestamps and observed RPO/RTO in release notes or operations logs.

## Release Owner Checklist

- Follow `docs/release.md` (including the V1.0 Release Checklist for major releases).
- Validate release notes follow `docs/release_notes_template.md` structure.
- Verify post-release workflows are green.
- For v1.0+: confirm `docs/v1_stabilization_checklist.md` sign-off is complete.

## V1 Contract Maintenance

After the v1.0 release, the contract surface is frozen. Follow these rules:

### Adding to the Contract

- New symbols may be added to `eap.protocol`, `eap.environment`, `eap.agent`, or `eap.runtime` without a breaking change.
- Update `docs/v1_contract_lock.json` in the same PR and bump the minor version.
- CI enforces lock consistency via `scripts/check_v1_contract.py`.

### Removing or Changing Contract Surface

- Removing or renaming any frozen symbol, field, or behavior is a **breaking change**.
- Breaking changes require a **major version bump** (v2.0+).
- Emit `DeprecationWarning` for at least one minor release before removal.
- Document the change in `Breaking Changes` and `Upgrade Notes` in release notes.

### Handling Contract Test Failures

- If `tests/contract/` tests fail on a PR, the change likely violates the v1 contract.
- Evaluate whether the change is intentional (contract evolution) or accidental (regression).
- Intentional changes must follow the removal/change process above.

### Ongoing Gate Validation

- Run `PYTHONPATH=. python scripts/v1_readiness_gatepack.py` periodically to verify all gates remain green.
- The gatepack runs automatically in CI on every push (py3.11 job).
- Gate documentation: `docs/v1_readiness_gates.md`.

## Response Expectations

- First maintainer response target:
  - issues: within 3 business days
  - PRs: within 3 business days
- If blocked, post status update within 7 days.

## Credentials and Access

- Keep repository admin and package publish access documented and rotated.
- Prefer PyPI Trusted Publishing for stable releases (avoid long-lived PyPI tokens in GitHub secrets).
- Keep branch protection enabled on `main`.
- Ensure at least two maintainers have workflow/release access when team size allows.

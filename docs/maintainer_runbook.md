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

## Release Owner Checklist

- Follow `docs/release.md`.
- Validate release notes and migration implications.
- Verify post-release workflows are green.

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

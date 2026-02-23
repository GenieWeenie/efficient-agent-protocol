# Contributing

Thanks for contributing to Efficient Agent Protocol (EAP).

## Workflow

1. Create a branch from `main` using `codex/` or `feature/` prefix.
2. Keep changes focused and scoped to one objective.
3. Run local checks before opening a PR.
4. Open a PR with a clear summary and validation steps.

## Local Validation

```bash
python3 -m pytest -q
python3 -m pre_commit run --all-files
python3 -m pip_audit -r requirements.txt
```

## Pull Request Expectations

- Link the roadmap issue (`Closes #<id>` or `Partially addresses #<id>`).
- Include risk notes for behavioral changes.
- Include migration notes if schema/state format changes.
- Keep PRs small enough for fast review.

## Issue and PR Response Expectations

- New issues: first maintainer response target is within 3 business days.
- New PRs: first maintainer review target is within 3 business days.
- If blocked or delayed, maintainers should post a status update within 7 days.

## Release and Migration Notes

- Follow `docs/release.md` for release procedure and rollback.
- Follow `docs/migrations.md` for schema/state migration policy.

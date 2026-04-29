# GitHub Actions Runtime Inventory

Status: Active for `EAP-131` / `GEN-211`  
Last reviewed: 2026-04-29

## Purpose

Track JavaScript GitHub Actions that can emit Node.js runtime deprecation warnings so release evidence stays clean and explainable.

## Resolution Summary

Most workflow actions now use upstream majors that declare `runs.using: node24`:

| Action family | Previous pin | Current pin | Runtime status |
| --- | --- | --- | --- |
| `actions/checkout` | `v4` | `v6` | Node 24 |
| `actions/setup-python` | `v5` | `v6` | Node 24 |
| `actions/setup-node` | `v4` | `v6` | Node 24 |
| `actions/upload-artifact` | `v4` | `v7` | Node 24 |
| `actions/download-artifact` | `v4` | `v8` | Node 24 |
| `release-drafter/release-drafter` | `v6` | `v7` | Node 24 |
| `github/codeql-action/*` | `v4` | `v4` | Node 24 already |
| `pypa/gh-action-pypi-publish` | `release/v1` | `release/v1` | Composite action, no JavaScript runtime warning |

`gitleaks/gitleaks-action@v2` still declares `runs.using: node20`, so the Security workflow now installs and runs the pinned Gitleaks CLI directly instead of invoking the JavaScript action.

## Remaining Upstream Blocker

`actions/dependency-review-action@v4` still declares `runs.using: node20` as of 2026-04-29, and no Node 24-compatible major is published yet. The job remains PR-only and opt-in behind `vars.ENABLE_DEPENDENCY_REVIEW == 'true'`.

Temporary mitigation:

- The step sets `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` so GitHub-hosted runners use the Node 24 compatibility path.
- Keep this documented until `actions/dependency-review-action@v5` or another Node 24-compatible major exists.
- Do not loosen workflow permissions while carrying this blocker; the job still requests only `contents: read` and `pull-requests: read`.

## Validation

For future release evidence, verify:

```bash
rg -n "actions/(checkout@v4|setup-python@v5|setup-node@v4|upload-artifact@v4|download-artifact@v4)|gitleaks/gitleaks-action@v2|release-drafter/release-drafter@v6" .github/workflows
python -m pytest -q tests/contract/test_github_actions_runtime_contract.py
```

The first command should return no matches. Any remaining GitHub annotation should map to the Dependency Review upstream blocker above.

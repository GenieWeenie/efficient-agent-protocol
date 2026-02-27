# V1.0 Go/No-Go Checklist

This checklist determines whether the project is ready to cut the `v1.0.0` tag.
Every item must be checked before promoting a release candidate to stable.

## RC Dry-Run Procedure

Execute these steps for each release candidate (`v1.0.0-rc1`, `v1.0.0-rc2`, etc.):

### 1. Prepare the RC

```bash
# Ensure main is up to date
git checkout main && git pull origin main

# Create RC branch
git checkout -b release/v1.0.0-rc1

# Bump version in pyproject.toml to 1.0.0rc1
# (edit pyproject.toml: version = "1.0.0rc1")

# Commit and push
git add pyproject.toml
git commit -m "Bump version to 1.0.0rc1 for RC dry-run"
git push -u origin release/v1.0.0-rc1
```

### 2. Run Local Validation

```bash
# Full readiness gatepack (9 gates)
PYTHONPATH=. python scripts/v1_readiness_gatepack.py

# Contract lock check
PYTHONPATH=. python scripts/check_v1_contract.py --skip-version-history-check

# Full test suite
PYTHONPATH=. python -m pytest -q
```

### 3. Tag and Trigger Release Workflow

```bash
git tag v1.0.0-rc1
git push origin v1.0.0-rc1
```

This triggers `.github/workflows/release.yml`, which:
- Validates tag/package version alignment.
- Builds distribution artifacts.
- Publishes to TestPyPI (RC tags use `TEST_PYPI_API_TOKEN`).

### 4. Validate TestPyPI Publication

```bash
# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  efficient-agent-protocol==1.0.0rc1

# Verify import and version
python -c "import eap; print(eap.__version__)"

# Run smoke test
python -m examples.01_minimal
```

### 5. Verify CI

- Confirm the release workflow run is green on GitHub Actions.
- Confirm all CI checks on `main` are passing.
- Confirm security workflows (Gitleaks, CodeQL, pip-audit) are green.

### 6. Record Evidence

Document the following for each RC:

| Evidence | Location |
| --- | --- |
| Gatepack output (9/9 PASS) | Terminal output or CI log |
| CI release workflow run URL | GitHub Actions |
| TestPyPI package URL | `https://test.pypi.org/project/efficient-agent-protocol/1.0.0rc1/` |
| Install smoke test result | Terminal output |
| Security scan results | GitHub Security tab |

---

## Go/No-Go Decision Criteria

### Must-Pass (blocking)

- [ ] All 9 readiness gates pass (`scripts/v1_readiness_gatepack.py` reports `PASS 9/9`).
- [ ] `docs/v1_stabilization_checklist.md` — all stabilization items checked.
- [ ] CI green on `main`: lint/test (py3.9, 3.10, 3.11), coverage gates, contract gate, upgrade migration, eval scorecard, competitive benchmark, soak+chaos, security scans.
- [ ] RC release workflow succeeds (build + TestPyPI publish).
- [ ] RC installs cleanly from TestPyPI and passes smoke test.
- [ ] `docs/upgrade_notes_v1.md` covers all 5 required sections (scope, breaking changes, migration, verification, rollback).
- [ ] `docs/v1_contract_lock.json` matches intended v1.0 surface.
- [ ] Release notes follow `docs/release_notes_template.md` structure.
- [ ] No open high-severity CodeQL alerts.
- [ ] No known vulnerabilities in `pip-audit`.

### Should-Pass (non-blocking but tracked)

- [ ] TestPyPI package installs and imports on Python 3.9, 3.10, and 3.11.
- [ ] Self-hosted stack smoke test passes against RC build.
- [ ] OpenClaw interop smoke tests pass.
- [ ] Documentation links in README all resolve.

### Owner Sign-Off

These sign-offs must be obtained before tagging `v1.0.0` (stable):

- [ ] **Engineering owner** — confirms code quality, test coverage, and contract stability.
- [ ] **Release owner** — confirms release process, CI gates, and package publication.
- [ ] **Documentation owner** — confirms docs accuracy, upgrade notes, and runbook completeness.

---

## Promoting RC to Stable

Once all must-pass criteria are met and sign-offs obtained:

```bash
# Bump version to stable
# (edit pyproject.toml: version = "1.0.0")

# Commit on main
git checkout main
git commit -am "Release v1.0.0"
git push origin main

# Tag stable release
git tag v1.0.0
git push origin v1.0.0
```

The stable tag triggers production PyPI publication via Trusted Publishing.

## Post-Release

After the stable `v1.0.0` tag:

1. Verify PyPI publication: `pip install efficient-agent-protocol==1.0.0`
2. Verify release workflow succeeded on GitHub Actions.
3. Update Linear/roadmap issues to Done.
4. Announce release in relevant channels.

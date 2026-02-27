# V1 Readiness Gates

This document maps every gate that must pass before cutting a `v1.0` release.
Run all gates with a single command:

```bash
PYTHONPATH=. python scripts/v1_readiness_gatepack.py
```

## Gate Summary

| # | Gate | Threshold / Criteria | Evidence Artifact |
| --- | --- | --- | --- |
| 1 | V1 contract lock | Runtime surface matches `docs/v1_contract_lock.json` | `scripts/check_v1_contract.py` output |
| 2 | Upgrade migration | v0.1.8 baseline DB upgrades with data preserved | `scripts/verify_upgrade_from_baseline.py` output |
| 3 | Contract tests | All `tests/contract/` tests pass | pytest output |
| 4 | Performance bounds | `tests/perf/` within hard upper bounds | pytest output |
| 5 | Reliability integration | Retry, timeout, dependency-failure tests pass | `tests/integration/test_reliability_failures.py` |
| 6 | Full test suite | All `tests/` pass | pytest output |
| 7 | Coverage | Line >= 80%, branch >= 65% | `coverage.json` |
| 8 | Dependency security | `pip-audit` reports zero vulnerabilities | pip-audit output |
| 9 | Threshold files | All baseline/threshold JSON files present | file existence check |

## Gate Details

### 1. V1 Contract Lock

Validates that the live Python export surface, workflow schemas, error
payload contract, and settings keys match the frozen lock file.

```bash
PYTHONPATH=. python scripts/check_v1_contract.py --skip-version-history-check
```

### 2. Upgrade Migration (v0.1.8 Baseline)

Creates a deterministic v0.1.8-compatible state database, applies pending
migrations, and validates schema version, table presence, data preservation,
`StateManager` operations, and rollback path.

```bash
PYTHONPATH=. python scripts/verify_upgrade_from_baseline.py
```

### 3. Contract Tests

Covers v1 contract lock, pointer lifecycle contract, observability contract,
workflow schema contract, public API contract, and proof-sheet contracts.

```bash
PYTHONPATH=. python -m pytest tests/contract/ -q
```

### 4. Performance Bounds

Hard upper-bound assertions on concurrency and rate-limit tests.

```bash
PYTHONPATH=. python -m pytest tests/perf/ -q
```

### 5. Reliability Integration Tests

Retry, timeout, and dependency-failure scenarios plus the upgrade baseline
round-trip.

```bash
PYTHONPATH=. python -m pytest \
  tests/integration/test_reliability_failures.py \
  tests/integration/test_upgrade_from_baseline.py -q
```

### 6. Full Test Suite

All unit, integration, contract, and performance tests.

```bash
PYTHONPATH=. python -m pytest tests/ -x -q
```

### 7. Coverage

Line coverage >= 80%, branch coverage >= 65% across `protocol`, `agent`,
`environment`, and `eap` modules.

```bash
PYTHONPATH=. python -m pytest tests/ -q \
  --cov=protocol --cov=agent --cov=environment --cov=eap \
  --cov-branch --cov-report=json:coverage.json
```

### 8. Dependency Security Audit

Zero known vulnerabilities in pinned dependencies.

```bash
pip-audit -r requirements.txt
```

### 9. Threshold / Baseline Files

All CI threshold and baseline files must be present and version-controlled:

- `docs/eval_thresholds.json`
- `docs/eval_baseline.json`
- `docs/soak_chaos_thresholds.json`
- `docs/soak_chaos_baseline.json`
- `docs/competitive_thresholds.json`
- `docs/competitive_reference_profiles.json`
- `docs/v1_contract_lock.json`

## CI Gates (Automated)

The following are enforced automatically by GitHub Actions CI on every push:

| CI Job | What it checks |
| --- | --- |
| Lint/Test (py3.9, 3.10, 3.11) | Full test suite on three Python versions |
| Coverage gates (py3.11) | Line/branch thresholds |
| V1 compatibility contract gate | Contract lock + contract tests |
| Upgrade migration verification | Baseline upgrade path |
| Eval scorecard | Correctness, reliability, latency thresholds |
| Competitive benchmark | Advantage gates vs reference profiles |
| Soak + chaos reliability | Failure rate, latency, chaos scenario pass rate |
| Dependency vulnerability audit | pip-audit scan |
| Secret scan (Gitleaks) | No leaked secrets |
| CodeQL analysis | No high-severity code scanning alerts |
| Build package | Wheel builds and installs cleanly |
| Quickstart smoke | Bootstrap + doctor flow succeeds |
| Self-hosted stack smoke | Runtime HTTP API starts and serves |

## Release Runbook Integration

Before tagging `v1.0`:

1. Run the gatepack locally: `PYTHONPATH=. python scripts/v1_readiness_gatepack.py`
2. Verify CI is green on the release branch.
3. Confirm `docs/v1_stabilization_checklist.md` is fully checked.
4. Tag and push the release.

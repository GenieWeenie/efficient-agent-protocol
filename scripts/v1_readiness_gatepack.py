#!/usr/bin/env python3
"""V1 Readiness Gatepack — one command to evaluate all v1 critical gates.

Exit codes:
    0 — all gates pass
    1 — one or more gates failed

Each gate produces a structured result with pass/fail and diagnostic info.
Run this script from the repository root with ``PYTHONPATH=.``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str
    evidence: str = ""


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def gate_v1_contract() -> GateResult:
    """Gate 1: V1 contract lock matches runtime surface."""
    result = _run([
        sys.executable, "scripts/check_v1_contract.py",
        "--skip-version-history-check",
    ])
    passed = result.returncode == 0
    return GateResult(
        name="V1 contract lock",
        passed=passed,
        detail=result.stdout.strip() if passed else result.stderr.strip(),
        evidence="docs/v1_contract_lock.json",
    )


def gate_upgrade_migration() -> GateResult:
    """Gate 2: Upgrade from v0.1.8 baseline succeeds."""
    result = _run([sys.executable, "scripts/verify_upgrade_from_baseline.py"])
    passed = result.returncode == 0
    if passed:
        payload = json.loads(result.stdout)
        detail = f"All {len(payload.get('checks', []))} checks passed"
    else:
        detail = result.stdout.strip() or result.stderr.strip()
    return GateResult(
        name="Upgrade migration (v0.1.8 baseline)",
        passed=passed,
        detail=detail,
        evidence="scripts/verify_upgrade_from_baseline.py output",
    )


def gate_test_suite() -> GateResult:
    """Gate 3: Full test suite passes."""
    result = _run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=line"],
        timeout=180,
    )
    passed = result.returncode == 0
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else "no output"
    return GateResult(
        name="Test suite",
        passed=passed,
        detail=summary,
        evidence="pytest output",
    )


def gate_coverage() -> GateResult:
    """Gate 4: Line >= 80%, branch >= 65%."""
    with tempfile.TemporaryDirectory(prefix="eap-cov-") as tmpdir:
        cov_json = os.path.join(tmpdir, "coverage.json")
        result = _run([
            sys.executable, "-m", "pytest", "tests/", "-q",
            "--cov=protocol", "--cov=agent", "--cov=environment", "--cov=eap",
            "--cov-branch",
            f"--cov-report=json:{cov_json}",
            "--cov-report=",
        ], timeout=180)
        if result.returncode != 0:
            return GateResult(
                name="Coverage gates",
                passed=False,
                detail=f"Tests failed (exit {result.returncode})",
            )
        try:
            totals = json.loads(Path(cov_json).read_text(encoding="utf-8"))["totals"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
            return GateResult(
                name="Coverage gates",
                passed=False,
                detail=f"Could not read coverage report: {exc}",
            )

        line_pct = float(totals["percent_covered"])
        num_branches = int(totals.get("num_branches", 0))
        covered_branches = int(totals.get("covered_branches", 0))
        branch_pct = 100.0 if num_branches == 0 else (covered_branches / num_branches) * 100.0

        line_ok = line_pct >= 80.0
        branch_ok = branch_pct >= 65.0
        passed = line_ok and branch_ok
        detail = f"line={line_pct:.1f}% (min 80%), branch={branch_pct:.1f}% (min 65%)"
        return GateResult(
            name="Coverage gates",
            passed=passed,
            detail=detail,
            evidence=cov_json,
        )


def gate_perf_bounds() -> GateResult:
    """Gate 5: Performance tests pass within upper bounds."""
    result = _run(
        [sys.executable, "-m", "pytest", "tests/perf/", "-q", "--tb=line"],
        timeout=60,
    )
    passed = result.returncode == 0
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else "no output"
    return GateResult(
        name="Performance bounds",
        passed=passed,
        detail=summary,
        evidence="tests/perf/",
    )


def gate_contract_tests() -> GateResult:
    """Gate 6: All contract tests pass."""
    result = _run(
        [sys.executable, "-m", "pytest", "tests/contract/", "-q", "--tb=line"],
        timeout=60,
    )
    passed = result.returncode == 0
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else "no output"
    return GateResult(
        name="Contract tests",
        passed=passed,
        detail=summary,
        evidence="tests/contract/",
    )


def gate_reliability_integration() -> GateResult:
    """Gate 7: Reliability integration tests pass."""
    result = _run(
        [sys.executable, "-m", "pytest",
         "tests/integration/test_reliability_failures.py",
         "tests/integration/test_upgrade_from_baseline.py",
         "-q", "--tb=line"],
        timeout=60,
    )
    passed = result.returncode == 0
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else "no output"
    return GateResult(
        name="Reliability integration tests",
        passed=passed,
        detail=summary,
        evidence="tests/integration/test_reliability_failures.py",
    )


def gate_security_audit() -> GateResult:
    """Gate 8: pip-audit finds no vulnerabilities."""
    req_path = REPO_ROOT / "requirements.txt"
    if not req_path.exists():
        return GateResult(
            name="Dependency security audit",
            passed=True,
            detail="requirements.txt not found; skipped",
        )
    probe = _run([sys.executable, "-m", "pip_audit", "--version"], timeout=10)
    if probe.returncode != 0:
        return GateResult(
            name="Dependency security audit",
            passed=True,
            detail="pip-audit not installed; skipped (enforced in CI)",
        )
    result = _run(
        [sys.executable, "-m", "pip_audit", "-r", "requirements.txt"],
        timeout=60,
    )
    passed = result.returncode == 0
    detail = "No vulnerabilities found" if passed else result.stdout.strip()[:300]
    return GateResult(
        name="Dependency security audit",
        passed=passed,
        detail=detail,
        evidence="pip-audit output",
    )


def gate_threshold_files() -> GateResult:
    """Gate 9: Required threshold/baseline files exist."""
    required = [
        "docs/eval_thresholds.json",
        "docs/eval_baseline.json",
        "docs/soak_chaos_thresholds.json",
        "docs/soak_chaos_baseline.json",
        "docs/competitive_thresholds.json",
        "docs/competitive_reference_profiles.json",
        "docs/v1_contract_lock.json",
    ]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    passed = len(missing) == 0
    detail = "All threshold/baseline files present" if passed else f"Missing: {missing}"
    return GateResult(
        name="Threshold/baseline files",
        passed=passed,
        detail=detail,
    )


GATES = [
    gate_v1_contract,
    gate_upgrade_migration,
    gate_contract_tests,
    gate_perf_bounds,
    gate_reliability_integration,
    gate_test_suite,
    gate_coverage,
    gate_security_audit,
    gate_threshold_files,
]


def run_gatepack() -> dict[str, object]:
    results: List[GateResult] = []
    for gate_fn in GATES:
        try:
            result = gate_fn()
        except Exception as exc:
            result = GateResult(name=gate_fn.__doc__ or gate_fn.__name__, passed=False, detail=str(exc))
        results.append(result)

    all_passed = all(r.passed for r in results)
    return {
        "status": "PASS" if all_passed else "FAIL",
        "gates_total": len(results),
        "gates_passed": sum(1 for r in results if r.passed),
        "gates_failed": sum(1 for r in results if not r.passed),
        "gates": [
            {
                "name": r.name,
                "passed": r.passed,
                "detail": r.detail,
                "evidence": r.evidence,
            }
            for r in results
        ],
    }


def main() -> int:
    print("=" * 60)
    print("  V1 Readiness Gatepack")
    print("=" * 60)

    report = run_gatepack()

    for gate in report["gates"]:
        icon = "PASS" if gate["passed"] else "FAIL"
        print(f"\n  [{icon}] {gate['name']}")
        print(f"         {gate['detail']}")

    print("\n" + "=" * 60)
    status = report["status"]
    passed = report["gates_passed"]
    total = report["gates_total"]
    print(f"  Result: {status}  ({passed}/{total} gates passed)")
    print("=" * 60)

    print(json.dumps(report, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

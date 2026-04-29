#!/usr/bin/env python3
"""Production-hardening regression gatepack for Phase 13 fixes.

Exit codes:
    0 - all hardening gates pass
    1 - one or more hardening gates failed

Run from the repository root with ``PYTHONPATH=.``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class HardeningGate:
    name: str
    risk_class: str
    command: list[str]
    evidence: str
    known_bad_fixture: str
    timeout_seconds: int = 90


@dataclass(frozen=True)
class GateResult:
    name: str
    risk_class: str
    passed: bool
    detail: str
    command: list[str]
    evidence: str
    known_bad_fixture: str


HARDENING_GATES = [
    HardeningGate(
        name="Package ownership and canonical imports",
        risk_class="duplicate package trees / ambiguous runtime ownership",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/contract/test_package_namespace_contract.py",
            "tests/contract/test_canonical_import_references.py",
            "-q",
            "--tb=line",
        ],
        evidence="tests/contract/test_package_namespace_contract.py; tests/contract/test_canonical_import_references.py",
        known_bad_fixture="fails if legacy top-level packages become real implementations or docs/tests drift back to legacy imports",
    ),
    HardeningGate(
        name="Runtime ASGI boundary and fail-closed auth",
        risk_class="per-request event loop server path / anonymous trusted runtime access",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/contract/test_runtime_asgi_contract.py",
            "tests/contract/test_runtime_auth_scopes.py",
            "tests/integration/test_runtime_http_api.py::RuntimeHttpApiIntegrationTest::test_execute_macro_rejects_missing_auth",
            "tests/integration/test_runtime_http_api.py::RuntimeHttpApiIntegrationTest::test_execute_macro_rejects_oversized_request_body",
            "-q",
            "--tb=line",
        ],
        evidence="tests/contract/test_runtime_asgi_contract.py; tests/contract/test_runtime_auth_scopes.py; tests/integration/test_runtime_http_api.py",
        known_bad_fixture="fails if ThreadingHTTPServer/asyncio.run returns, auth fails open, or request body caps are removed",
    ),
    HardeningGate(
        name="Filesystem sandbox regressions",
        risk_class="unrestricted local file read/write/list access",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_tools.py::ToolModuleTest::test_file_tools_reject_traversal_escape",
            "tests/unit/test_tools.py::ToolModuleTest::test_file_tools_reject_absolute_escape",
            "tests/unit/test_tools.py::ToolModuleTest::test_file_tools_reject_symlink_escape",
            "tests/unit/test_tools.py::ToolModuleTest::test_file_tool_root_env_configures_default_sandbox",
            "-q",
            "--tb=line",
        ],
        evidence="tests/unit/test_tools.py",
        known_bad_fixture="fails if path traversal, absolute escapes, symlink escapes, or sandbox-root configuration regress",
    ),
    HardeningGate(
        name="Web SSRF and streaming byte caps",
        risk_class="SSRF exposure / post-load response size limiting",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_tools.py::ToolModuleTest::test_web_tools_reject_private_and_localhost_targets",
            "tests/unit/test_tools.py::ToolModuleTest::test_web_tools_recheck_redirect_targets_for_ssrf",
            "tests/unit/test_tools.py::ToolModuleTest::test_web_tools_streaming_byte_cap_stops_early",
            "-q",
            "--tb=line",
        ],
        evidence="tests/unit/test_tools.py",
        known_bad_fixture="fails if private/link-local/localhost DNS targets, unsafe redirects, or streaming byte caps are no longer enforced",
    ),
    HardeningGate(
        name="Macro cycle and timeout safety",
        risk_class="macro dependency cycles / unbounded macro execution",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_executor_errors.py::ExecutorErrorContractTest::test_direct_dependency_cycle_is_rejected",
            "tests/unit/test_executor_errors.py::ExecutorErrorContractTest::test_indirect_dependency_cycle_is_rejected",
            "tests/unit/test_executor_errors.py::ExecutorErrorContractTest::test_macro_total_timeout_returns_structured_error_pointer",
            "tests/integration/test_runtime_http_api.py::RuntimeHttpApiIntegrationTest::test_execute_macro_rejects_dependency_cycle",
            "-q",
            "--tb=line",
        ],
        evidence="tests/unit/test_executor_errors.py; tests/integration/test_runtime_http_api.py",
        known_bad_fixture="fails if direct/indirect cycles compile or total macro timeouts stop returning structured macro_timeout errors",
    ),
    HardeningGate(
        name="Bounded network lifecycle",
        risk_class="unbounded HTTP sessions / missing timeout and pool controls",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_http_client.py",
            "tests/unit/test_openclaw_client.py",
            "-q",
            "--tb=line",
        ],
        evidence="tests/unit/test_http_client.py; tests/unit/test_openclaw_client.py",
        known_bad_fixture="fails if critical network clients stop using bounded connect/read timeouts, retries, or owned-session lifecycle cleanup",
    ),
]


def _run(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def _summarize_output(result: subprocess.CompletedProcess[str]) -> str:
    output = result.stdout.strip() or result.stderr.strip()
    if not output:
        return f"exit={result.returncode}"
    lines = output.splitlines()
    return lines[-1] if result.returncode == 0 else output[-800:]


def run_gatepack() -> dict[str, object]:
    results: List[GateResult] = []
    for gate in HARDENING_GATES:
        try:
            completed = _run(gate.command, timeout_seconds=gate.timeout_seconds)
            passed = completed.returncode == 0
            detail = _summarize_output(completed)
        except subprocess.TimeoutExpired as exc:
            passed = False
            detail = f"Timed out after {exc.timeout}s"
        results.append(
            GateResult(
                name=gate.name,
                risk_class=gate.risk_class,
                passed=passed,
                detail=detail,
                command=gate.command,
                evidence=gate.evidence,
                known_bad_fixture=gate.known_bad_fixture,
            )
        )

    all_passed = all(result.passed for result in results)
    return {
        "status": "PASS" if all_passed else "FAIL",
        "gates_total": len(results),
        "gates_passed": sum(1 for result in results if result.passed),
        "gates_failed": sum(1 for result in results if not result.passed),
        "gates": [
            {
                "name": result.name,
                "risk_class": result.risk_class,
                "passed": result.passed,
                "detail": result.detail,
                "command": result.command,
                "evidence": result.evidence,
                "known_bad_fixture": result.known_bad_fixture,
            }
            for result in results
        ],
    }


def main() -> int:
    if "--json-only" in sys.argv:
        report = run_gatepack()
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "PASS" else 1

    print("=" * 72)
    print("  Production Hardening Regression Gatepack")
    print("=" * 72)

    report = run_gatepack()
    for gate in report["gates"]:
        icon = "PASS" if gate["passed"] else "FAIL"
        print(f"\n  [{icon}] {gate['name']}")
        print(f"         Risk: {gate['risk_class']}")
        print(f"         {gate['detail']}")

    print("\n" + "=" * 72)
    print(f"  Result: {report['status']}  ({report['gates_passed']}/{report['gates_total']} gates passed)")
    print("=" * 72)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

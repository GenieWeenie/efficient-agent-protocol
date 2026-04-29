from scripts.production_hardening_gatepack import HARDENING_GATES
from scripts.v1_readiness_gatepack import GATES, gate_production_hardening


REQUIRED_RISK_FRAGMENTS = [
    "duplicate package trees",
    "anonymous trusted runtime access",
    "unrestricted local file",
    "SSRF exposure",
    "macro dependency cycles",
    "unbounded HTTP sessions",
]

REQUIRED_TEST_TARGETS = [
    "tests/contract/test_package_namespace_contract.py",
    "tests/contract/test_canonical_import_references.py",
    "tests/contract/test_runtime_asgi_contract.py",
    "tests/contract/test_runtime_auth_scopes.py",
    "test_execute_macro_rejects_missing_auth",
    "test_execute_macro_rejects_oversized_request_body",
    "test_file_tools_reject_traversal_escape",
    "test_file_tools_reject_absolute_escape",
    "test_file_tools_reject_symlink_escape",
    "test_web_tools_reject_private_and_localhost_targets",
    "test_web_tools_recheck_redirect_targets_for_ssrf",
    "test_web_tools_streaming_byte_cap_stops_early",
    "test_direct_dependency_cycle_is_rejected",
    "test_indirect_dependency_cycle_is_rejected",
    "test_macro_total_timeout_returns_structured_error_pointer",
    "test_execute_macro_rejects_dependency_cycle",
    "tests/unit/test_http_client.py",
    "tests/unit/test_openclaw_client.py",
]


def _gate_commands() -> str:
    return "\n".join(" ".join(gate.command) for gate in HARDENING_GATES)


def test_hardening_gatepack_covers_all_phase13_risk_classes() -> None:
    risks = "\n".join(gate.risk_class for gate in HARDENING_GATES)

    for fragment in REQUIRED_RISK_FRAGMENTS:
        assert fragment in risks


def test_hardening_gatepack_targets_direct_regression_tests() -> None:
    commands = _gate_commands()

    for target in REQUIRED_TEST_TARGETS:
        assert target in commands


def test_hardening_gatepack_documents_known_bad_fixtures() -> None:
    for gate in HARDENING_GATES:
        assert gate.known_bad_fixture
        assert "fails if" in gate.known_bad_fixture
        assert gate.evidence


def test_v1_readiness_gatepack_runs_production_hardening_gate() -> None:
    assert gate_production_hardening in GATES

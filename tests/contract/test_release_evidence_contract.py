from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_INDEX = REPO_ROOT / "docs" / "README.md"
RELEASE_RUNBOOK = REPO_ROOT / "docs" / "release.md"
READINESS_EVIDENCE = REPO_ROOT / "docs" / "releases" / "v1.0.1-readiness.md"
PHASE14_ROADMAP = REPO_ROOT / "docs" / "phase14_release_maintenance_roadmap.md"
EXECUTION_PROTOCOL = REPO_ROOT / "docs" / "execution_protocol.md"


def test_v101_readiness_evidence_is_indexed() -> None:
    index_text = DOC_INDEX.read_text(encoding="utf-8")
    runbook_text = RELEASE_RUNBOOK.read_text(encoding="utf-8")

    assert "releases/v1.0.1-readiness.md" in index_text
    assert "releases/v1.0.1-readiness.md" in runbook_text


def test_v101_readiness_evidence_lists_required_gates_and_blocker() -> None:
    text = READINESS_EVIDENCE.read_text(encoding="utf-8")

    required_fragments = (
        "scripts/v1_readiness_gatepack.py",
        "scripts/production_hardening_gatepack.py",
        "python -m build",
        "docs/github_actions_runtime_inventory.md",
        "EAP-133",
        "GEN-213",
        "actions/dependency-review-action@v4",
    )
    for fragment in required_fragments:
        assert fragment in text


def test_phase14_marks_eap132_complete_and_eap133_next() -> None:
    phase_text = PHASE14_ROADMAP.read_text(encoding="utf-8")
    execution_text = EXECUTION_PROTOCOL.read_text(encoding="utf-8")

    assert "[x] `EAP-132` refresh release evidence and docs index (`GEN-212`)" in phase_text
    assert "| 45 | `EAP-132` | `GEN-212` | `Done` |" in execution_text
    assert "`EAP-133` is the next ordered `Todo`" in execution_text

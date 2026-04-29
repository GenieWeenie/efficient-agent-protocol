from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
INVENTORY_PATH = REPO_ROOT / "docs" / "github_actions_runtime_inventory.md"

NODE20_ACTION_PINS = (
    "actions/checkout@v4",
    "actions/setup-python@v5",
    "actions/setup-node@v4",
    "actions/upload-artifact@v4",
    "actions/download-artifact@v4",
    "gitleaks/gitleaks-action@v2",
    "release-drafter/release-drafter@v6",
)

EXPECTED_NODE24_PINS = (
    "actions/checkout@v6",
    "actions/setup-python@v6",
    "actions/setup-node@v6",
    "actions/upload-artifact@v7",
    "actions/download-artifact@v8",
    "release-drafter/release-drafter@v7",
)


def _workflow_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOWS_DIR.glob("*.yml"))
    )


def test_workflows_no_longer_use_known_node20_action_pins() -> None:
    text = _workflow_text()

    for action_pin in NODE20_ACTION_PINS:
        assert action_pin not in text


def test_workflows_use_expected_node24_action_pins() -> None:
    text = _workflow_text()

    for action_pin in EXPECTED_NODE24_PINS:
        assert action_pin in text


def test_dependency_review_blocker_is_documented_and_mitigated() -> None:
    workflow_text = _workflow_text()
    inventory_text = INVENTORY_PATH.read_text(encoding="utf-8")

    assert "actions/dependency-review-action@v4" in workflow_text
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in workflow_text
    assert "actions/dependency-review-action@v4" in inventory_text
    assert "upstream blocker" in inventory_text.lower()

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def test_project_license_uses_pep639_spdx_expression() -> None:
    text = PYPROJECT_PATH.read_text(encoding="utf-8")

    assert 'license = "MIT"' in text
    assert 'license = {' not in text
    assert 'license-files = ["LICENSE"]' in text

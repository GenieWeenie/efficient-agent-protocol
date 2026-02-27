"""Contract tests: README and docs alignment for v1 posture."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"


def _pyproject_version() -> str:
    for line in (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    raise RuntimeError("version not found in pyproject.toml")


class ReadmeDocLinksTest(unittest.TestCase):
    """Every local doc/file path referenced in the README must exist."""

    _LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

    def test_all_local_links_resolve(self) -> None:
        readme = README.read_text(encoding="utf-8")
        broken: list[str] = []
        for _label, target in self._LINK_RE.findall(readme):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (REPO_ROOT / target).resolve()
            if not path.exists():
                broken.append(target)
        self.assertEqual(broken, [], f"Broken local links in README: {broken}")

    def test_doc_index_links_resolve(self) -> None:
        doc_index = REPO_ROOT / "docs" / "README.md"
        if not doc_index.exists():
            self.skipTest("docs/README.md not found")
        text = doc_index.read_text(encoding="utf-8")
        broken: list[str] = []
        for _label, target in self._LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            base = REPO_ROOT / "docs"
            path = (base / target).resolve()
            if not path.exists():
                path = (REPO_ROOT / target).resolve()
            if not path.exists():
                broken.append(target)
        self.assertEqual(broken, [], f"Broken local links in docs/README.md: {broken}")


class ReadmeVersionConsistencyTest(unittest.TestCase):
    """Version references in README match pyproject.toml."""

    def test_latest_release_matches_pyproject(self) -> None:
        version = _pyproject_version()
        readme = README.read_text(encoding="utf-8")
        m = re.search(r"Latest(?:\s+stable)?\s+release:\s*`v?([\d.]+(?:rc\d+)?)`", readme)
        self.assertIsNotNone(m, "Latest release line not found in README")
        self.assertEqual(
            m.group(1),  # type: ignore[union-attr]
            version,
            f"README latest release ({m.group(1)}) != pyproject.toml ({version})",  # type: ignore[union-attr]
        )


class ReadmeRequiredSectionsTest(unittest.TestCase):
    """README contains all expected top-level sections."""

    REQUIRED_HEADINGS = [
        "Quickstart",
        "Why Choose EAP",
        "What You Get",
        "Current Limits",
        "Programmatic Example",
        "Docs",
    ]

    def test_required_sections_present(self) -> None:
        readme = README.read_text(encoding="utf-8")
        for heading in self.REQUIRED_HEADINGS:
            pattern = re.compile(rf"^##\s.*{re.escape(heading)}", re.MULTILINE)
            self.assertRegex(
                readme,
                pattern,
                f"Missing required README section containing '{heading}'",
            )


class StabilityDocAlignmentTest(unittest.TestCase):
    """STABILITY.md must not contradict v1 contract posture."""

    def test_no_experimental_pre1_language(self) -> None:
        stability = (REPO_ROOT / "STABILITY.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "pre-1.0 (experimental)",
            stability,
            "STABILITY.md still contains outdated 'pre-1.0 (experimental)' language",
        )

    def test_references_v1_contract(self) -> None:
        stability = (REPO_ROOT / "STABILITY.md").read_text(encoding="utf-8")
        self.assertIn("v1_contract.md", stability)


if __name__ == "__main__":
    unittest.main()

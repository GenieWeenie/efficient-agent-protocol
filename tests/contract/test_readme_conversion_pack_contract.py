import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"


class ReadmeConversionPackContractTest(unittest.TestCase):
    def test_required_badges_and_media_are_present_near_top(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        top_boundary = readme.find("## Why Choose EAP")
        self.assertGreater(top_boundary, 0)
        top = readme[:top_boundary]

        required_snippets = [
            "actions/workflows/ci.yml/badge.svg",
            "coverage-gated%20in%20CI",
            "python-3.9--3.13-blue",
            "img.shields.io/github/v/release/GenieWeenie/efficient-agent-protocol",
            "assets/readme/eap_demo.gif",
            "assets/readme/eap_architecture.jpg",
        ]
        for snippet in required_snippets:
            self.assertIn(snippet, top, msg=f"Missing required README top-section element: {snippet}")

    def test_readme_local_media_links_exist(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        image_links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
        self.assertGreater(len(image_links), 0)

        for link in image_links:
            if "://" in link:
                continue
            if link.startswith("#"):
                continue
            target = (REPO_ROOT / link).resolve()
            self.assertTrue(target.exists(), msg=f"README media link target missing: {link}")

    def test_readme_media_assets_are_lightweight(self) -> None:
        gif_path = REPO_ROOT / "assets/readme/eap_demo.gif"
        arch_path = REPO_ROOT / "assets/readme/eap_architecture.jpg"

        self.assertTrue(gif_path.exists(), "Demo GIF is missing.")
        self.assertTrue(arch_path.exists(), "Architecture image is missing.")

        self.assertLessEqual(gif_path.stat().st_size, 1_000_000, "Demo GIF exceeds 1MB.")
        self.assertLessEqual(arch_path.stat().st_size, 1_000_000, "Architecture image exceeds 1MB.")


if __name__ == "__main__":
    unittest.main()

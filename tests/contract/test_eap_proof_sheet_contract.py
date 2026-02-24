import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_proof_sheet.py"


class EAPProofSheetContractTest(unittest.TestCase):
    def test_verify_script_passes_for_repository_proof_sheet(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(VERIFY_SCRIPT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)

    def test_verify_script_fails_when_referenced_paths_are_missing(self) -> None:
        proof_markdown = """# EAP Proof Sheet: Why EAP Now

## Side-by-Side Capability Table

| Capability | EAP runtime status | OpenClaw interop status | Evidence |
| --- | --- | --- | --- |
| Broken row | test | test | `scripts/missing_file.py`, `docs/missing_doc.md` |

## Reproducible Commands

```bash
python scripts/missing_file.py
```
"""

        with tempfile.TemporaryDirectory(prefix="eap-proof-sheet-contract-") as temp_dir:
            temp_root = Path(temp_dir)
            proof_path = temp_root / "proof.md"
            proof_path.write_text(proof_markdown, encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_SCRIPT),
                    "--proof-sheet",
                    str(proof_path),
                    "--repo-root",
                    str(temp_root),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1)
            combined_output = completed.stdout + completed.stderr
            self.assertIn("scripts/missing_file.py", combined_output)
            self.assertIn("docs/missing_doc.md", combined_output)


if __name__ == "__main__":
    unittest.main()

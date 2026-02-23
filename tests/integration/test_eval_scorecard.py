import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class EvalScorecardIntegrationTest(unittest.TestCase):
    def test_eval_scorecard_generates_artifacts_and_passes_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-eval-artifacts-") as temp_dir:
            output_dir = Path(temp_dir) / "eval"
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "eval_scorecard.py"),
                "--output-dir",
                str(output_dir),
                "--threshold-config",
                str(REPO_ROOT / "docs" / "eval_thresholds.json"),
                "--baseline",
                str(REPO_ROOT / "docs" / "eval_baseline.json"),
                "--latency-iterations",
                "8",
            ]
            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)

            scorecard_path = output_dir / "scorecard.json"
            markdown_path = output_dir / "scorecard.md"
            trend_path = output_dir / "trend.json"
            history_path = output_dir / "history.ndjson"
            self.assertTrue(scorecard_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertTrue(trend_path.exists())
            self.assertTrue(history_path.exists())

            scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
            self.assertIn("correctness", scorecard)
            self.assertIn("reliability", scorecard)
            self.assertIn("latency_ms", scorecard)
            self.assertTrue(scorecard["gate"]["passed"])


if __name__ == "__main__":
    unittest.main()

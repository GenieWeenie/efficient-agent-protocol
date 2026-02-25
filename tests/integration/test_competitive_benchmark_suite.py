import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class CompetitiveBenchmarkSuiteIntegrationTest(unittest.TestCase):
    def test_suite_generates_artifacts_and_passes_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-competitive-suite-") as temp_dir:
            output_dir = Path(temp_dir) / "competitive"
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "competitive_benchmark_suite.py"),
                "--output-dir",
                str(output_dir),
                "--profiles",
                str(REPO_ROOT / "docs" / "competitive_reference_profiles.json"),
                "--threshold-config",
                str(REPO_ROOT / "docs" / "competitive_thresholds.json"),
                "--eval-threshold-config",
                str(REPO_ROOT / "docs" / "eval_thresholds.json"),
                "--eval-baseline",
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

            json_path = output_dir / "comparison_scorecard.json"
            markdown_path = output_dir / "comparison_scorecard.md"
            manifest_path = output_dir / "manifest.json"
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertTrue(manifest_path.exists())

            scorecard = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(scorecard["gate"]["passed"])
            self.assertGreaterEqual(scorecard["reference_profile_count"], 2)
            self.assertIn("eap_metrics", scorecard)
            self.assertIn("reference_matrix", scorecard)

    def test_suite_fails_when_thresholds_are_unreachable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-competitive-suite-fail-") as temp_dir:
            output_dir = Path(temp_dir) / "competitive"
            strict_thresholds = Path(temp_dir) / "strict_thresholds.json"
            strict_thresholds.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "required_reference_profiles": 2,
                        "metrics": {
                            "min_correctness_pass_rate": 1.1,
                            "min_reliability_pass_rate": 1.1,
                            "max_latency_p95_ms": 1.0,
                        },
                        "advantage": {
                            "min_correctness_delta": 0.5,
                            "min_reliability_delta": 0.8,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "competitive_benchmark_suite.py"),
                "--output-dir",
                str(output_dir),
                "--profiles",
                str(REPO_ROOT / "docs" / "competitive_reference_profiles.json"),
                "--threshold-config",
                str(strict_thresholds),
                "--eval-threshold-config",
                str(REPO_ROOT / "docs" / "eval_thresholds.json"),
                "--eval-baseline",
                str(REPO_ROOT / "docs" / "eval_baseline.json"),
                "--latency-iterations",
                "6",
            ]
            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1, msg=completed.stdout + completed.stderr)
            scorecard = json.loads((output_dir / "comparison_scorecard.json").read_text(encoding="utf-8"))
            self.assertFalse(scorecard["gate"]["passed"])
            self.assertGreater(len(scorecard["gate"]["failures"]), 0)


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class SoakChaosScorecardIntegrationTest(unittest.TestCase):
    def test_soak_chaos_scorecard_generates_artifacts_and_passes_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-soak-chaos-") as temp_dir:
            output_dir = Path(temp_dir) / "soak_chaos"
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "soak_chaos_scorecard.py"),
                "--output-dir",
                str(output_dir),
                "--threshold-config",
                str(REPO_ROOT / "docs" / "soak_chaos_thresholds.json"),
                "--baseline",
                str(REPO_ROOT / "docs" / "soak_chaos_baseline.json"),
                "--soak-iterations",
                "42",
                "--soak-chaos-interval",
                "7",
                "--retry-storm-steps",
                "6",
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
            self.assertIn("soak", scorecard)
            self.assertIn("chaos", scorecard)
            self.assertTrue(scorecard["gate"]["passed"])
            self.assertGreaterEqual(int(scorecard["soak"]["total_runs"]), 42)
            self.assertEqual(int(scorecard["chaos"]["total"]), 3)

    def test_soak_chaos_scorecard_fails_when_thresholds_are_unreachable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-soak-chaos-fail-") as temp_dir:
            output_dir = Path(temp_dir) / "soak_chaos"
            strict_thresholds = Path(temp_dir) / "strict_soak_thresholds.json"
            strict_thresholds.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "soak": {
                            "min_runs": 80,
                            "max_failure_rate": 0.0,
                            "max_latency_p95_ms": 1.0,
                            "min_retry_events_total": 999,
                        },
                        "chaos": {
                            "min_pass_rate": 1.0,
                            "required_scenarios": [
                                "dependency_outage",
                                "timeout_recovery",
                                "retry_storm",
                            ],
                            "scenario_requirements": {
                                "retry_storm": {"min_retry_events": 999},
                            },
                        },
                        "regression": {
                            "max_failure_rate_increase": 0.0,
                            "max_latency_p95_ratio_increase": 0.0,
                            "max_chaos_pass_rate_drop": 0.0,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "soak_chaos_scorecard.py"),
                "--output-dir",
                str(output_dir),
                "--threshold-config",
                str(strict_thresholds),
                "--baseline",
                str(REPO_ROOT / "docs" / "soak_chaos_baseline.json"),
                "--soak-iterations",
                "24",
                "--soak-chaos-interval",
                "8",
                "--retry-storm-steps",
                "4",
            ]
            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1, msg=completed.stdout + completed.stderr)
            scorecard = json.loads((output_dir / "scorecard.json").read_text(encoding="utf-8"))
            self.assertFalse(scorecard["gate"]["passed"])
            self.assertGreater(len(scorecard["gate"]["failures"]), 0)


if __name__ == "__main__":
    unittest.main()

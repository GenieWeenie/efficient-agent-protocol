import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "bootstrap_local.sh"


class BootstrapLocalIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bootstrap_python = cls._find_supported_python()
        if cls.bootstrap_python is None:
            raise unittest.SkipTest("No Python 3.9-3.13 interpreter available for bootstrap integration tests.")

    @staticmethod
    def _find_supported_python() -> Optional[str]:
        candidates = (
            sys.executable,
            "python3.13",
            "python3.12",
            "python3.11",
            "python3.10",
            "python3.9",
            "python3",
        )
        for candidate in candidates:
            executable = shutil.which(candidate)
            if executable is None:
                continue
            completed = subprocess.run(
                [
                    executable,
                    "-c",
                    "import sys; raise SystemExit(0 if (3, 9) <= sys.version_info[:2] < (3, 14) else 1)",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                return executable
        return None

    def test_bootstrap_skip_install_is_idempotent_and_writes_trace_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-bootstrap-") as temp_dir:
            temp_root = Path(temp_dir)
            env_file = temp_root / ".env"
            artifact_dir = temp_root / "artifacts"
            db_path = artifact_dir / "bootstrap_state.db"
            artifact_path = artifact_dir / "bootstrap_trace.json"

            env_file.write_text(
                "\n".join(
                    [
                        "EAP_BASE_URL=http://localhost:1234",
                        "EAP_MODEL=nemotron-orchestrator-8b",
                        "EAP_API_KEY=not-needed",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            command = [
                "bash",
                str(BOOTSTRAP_SCRIPT),
                "--python",
                self.bootstrap_python,
                "--skip-install",
                "--env-file",
                str(env_file),
                "--artifact-dir",
                str(artifact_dir),
                "--db-path",
                str(db_path),
            ]

            first = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)

            self.assertTrue(artifact_path.exists(), "Bootstrap trace artifact must be generated.")
            payload_first = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertIn("run_id", payload_first)
            self.assertIn("pointer_id", payload_first)
            self.assertGreater(payload_first.get("trace_event_count", 0), 0)

            second = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)
            payload_second = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertNotEqual(payload_first["run_id"], payload_second["run_id"])

    def test_bootstrap_reports_env_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-bootstrap-env-") as temp_dir:
            temp_root = Path(temp_dir)
            env_file = temp_root / ".env"
            artifact_dir = temp_root / "artifacts"
            db_path = artifact_dir / "bootstrap_state.db"

            env_file.write_text(
                "\n".join(
                    [
                        "EAP_BASE_URL=localhost:1234",
                        "EAP_MODEL=",
                        "EAP_API_KEY=not-needed",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            command = [
                "bash",
                str(BOOTSTRAP_SCRIPT),
                "--python",
                self.bootstrap_python,
                "--skip-install",
                "--env-file",
                str(env_file),
                "--artifact-dir",
                str(artifact_dir),
                "--db-path",
                str(db_path),
            ]

            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            combined = completed.stdout + completed.stderr
            self.assertIn("Environment validation failed", combined)
            self.assertIn("EAP_BASE_URL must start with http:// or https://", combined)
            self.assertIn("EAP_MODEL is required and cannot be empty", combined)


if __name__ == "__main__":
    unittest.main()

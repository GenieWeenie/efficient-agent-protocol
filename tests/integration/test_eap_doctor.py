import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTOR_SCRIPT = REPO_ROOT / "scripts" / "eap_doctor.py"


class EAPDoctorIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ((3, 9) <= sys.version_info[:2] < (3, 14)):
            raise unittest.SkipTest("Doctor integration tests require Python 3.9-3.13.")

    def test_init_env_generates_runnable_env_and_doctor_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-doctor-init-") as temp_dir:
            temp_root = Path(temp_dir)
            env_file = temp_root / ".env"
            diagnostics_json = temp_root / "doctor.json"
            db_path = temp_root / "doctor_state.db"

            init_result = subprocess.run(
                [
                    sys.executable,
                    str(DOCTOR_SCRIPT),
                    "init-env",
                    "--output",
                    str(env_file),
                    "--force",
                    "--base-url",
                    "http://localhost:1234",
                    "--model",
                    "nemotron-orchestrator-8b",
                    "--openai-api-mode",
                    "chat_completions",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(init_result.returncode, 0, msg=init_result.stdout + init_result.stderr)
            self.assertTrue(env_file.exists(), "init-env should generate target .env file")

            doctor_result = subprocess.run(
                [
                    sys.executable,
                    str(DOCTOR_SCRIPT),
                    "doctor",
                    "--env-file",
                    str(env_file),
                    "--skip-connectivity",
                    "--state-db-path",
                    str(db_path),
                    "--output-json",
                    str(diagnostics_json),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(doctor_result.returncode, 0, msg=doctor_result.stdout + doctor_result.stderr)
            payload = json.loads(diagnostics_json.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["exit_code"], 0)
            self.assertIn("checks", payload)
            self.assertGreater(len(payload["checks"]), 0)

    def test_doctor_returns_connectivity_failure_bit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-doctor-connectivity-") as temp_dir:
            temp_root = Path(temp_dir)
            env_file = temp_root / ".env"
            diagnostics_json = temp_root / "doctor.json"
            db_path = temp_root / "doctor_state.db"

            env_file.write_text(
                "\n".join(
                    [
                        "EAP_BASE_URL=http://127.0.0.1:1",
                        "EAP_MODEL=nemotron-orchestrator-8b",
                        "EAP_API_KEY=not-needed",
                        "EAP_OPENAI_API_MODE=chat_completions",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            doctor_result = subprocess.run(
                [
                    sys.executable,
                    str(DOCTOR_SCRIPT),
                    "doctor",
                    "--env-file",
                    str(env_file),
                    "--state-db-path",
                    str(db_path),
                    "--output-json",
                    str(diagnostics_json),
                    "--connect-timeout-seconds",
                    "0.2",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(doctor_result.returncode, 0)
            self.assertEqual(doctor_result.returncode & 4, 4, "connectivity bit should be set")

            payload = json.loads(diagnostics_json.read_text(encoding="utf-8"))
            self.assertFalse(payload["ok"])
            self.assertIn("connectivity", payload["summary"]["failed_categories"])

    def test_doctor_returns_env_failure_bit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-doctor-env-") as temp_dir:
            temp_root = Path(temp_dir)
            env_file = temp_root / ".env"
            diagnostics_json = temp_root / "doctor.json"
            db_path = temp_root / "doctor_state.db"

            env_file.write_text(
                "\n".join(
                    [
                        "EAP_BASE_URL=http://localhost:1234",
                        "EAP_MODEL=",
                        "EAP_API_KEY=not-needed",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            doctor_result = subprocess.run(
                [
                    sys.executable,
                    str(DOCTOR_SCRIPT),
                    "doctor",
                    "--env-file",
                    str(env_file),
                    "--skip-connectivity",
                    "--state-db-path",
                    str(db_path),
                    "--output-json",
                    str(diagnostics_json),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(doctor_result.returncode, 0)
            self.assertEqual(doctor_result.returncode & 1, 1, "env bit should be set")

            payload = json.loads(diagnostics_json.read_text(encoding="utf-8"))
            self.assertFalse(payload["ok"])
            self.assertIn("env", payload["summary"]["failed_categories"])


if __name__ == "__main__":
    unittest.main()

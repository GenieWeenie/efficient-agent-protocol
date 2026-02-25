import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


REPO_ROOT = Path(__file__).resolve().parents[2]


def _echo_tool(value: str) -> str:
    return value


TOOL_SCHEMA = {
    "name": "echo_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    },
}


class AuditBundleIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-audit-bundle-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("echo_tool", _echo_tool, TOOL_SCHEMA)
        self.executor = AsyncLocalExecutor(self.state_manager, registry)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_export_and_verify_bundle_detects_tamper(self) -> None:
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="echo_tool", arguments={"value": "ok"})]
        )
        run_result = asyncio.run(self.executor.execute_macro(macro))
        self.assertIn("pointer_id", run_result)

        with tempfile.TemporaryDirectory(prefix="eap-audit-output-") as bundle_dir:
            export_cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "export_audit_bundle.py"),
                "--db-path",
                self.db_path,
                "--output-dir",
                bundle_dir,
            ]
            export_proc = subprocess.run(
                export_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(export_proc.returncode, 0, msg=export_proc.stdout + export_proc.stderr)

            verify_cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "verify_audit_bundle.py"),
                "--bundle-dir",
                bundle_dir,
            ]
            verify_proc = subprocess.run(
                verify_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify_proc.returncode, 0, msg=verify_proc.stdout + verify_proc.stderr)
            verify_payload = json.loads(verify_proc.stdout)
            self.assertTrue(verify_payload["verified"])

            trace_file = Path(bundle_dir) / "trace_events.json"
            trace_file.write_text(trace_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            tampered_proc = subprocess.run(
                verify_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(tampered_proc.returncode, 1, msg=tampered_proc.stdout + tampered_proc.stderr)
            tampered_payload = json.loads(tampered_proc.stdout)
            self.assertFalse(tampered_payload["verified"])
            self.assertTrue(
                any("file hash mismatch: trace_events.json" in error for error in tampered_payload["errors"])
            )

    def test_signed_bundle_requires_key_and_validates_signature(self) -> None:
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="echo_tool", arguments={"value": "ok"})]
        )
        asyncio.run(self.executor.execute_macro(macro))

        with tempfile.TemporaryDirectory(prefix="eap-audit-signed-output-") as bundle_dir:
            export_cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "export_audit_bundle.py"),
                "--db-path",
                self.db_path,
                "--output-dir",
                bundle_dir,
                "--signing-key",
                "integration-secret",
                "--signer-key-id",
                "ci",
            ]
            export_proc = subprocess.run(
                export_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(export_proc.returncode, 0, msg=export_proc.stdout + export_proc.stderr)

            verify_cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "verify_audit_bundle.py"),
                "--bundle-dir",
                bundle_dir,
            ]
            missing_key_proc = subprocess.run(
                verify_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                missing_key_proc.returncode, 1, msg=missing_key_proc.stdout + missing_key_proc.stderr
            )
            missing_key_payload = json.loads(missing_key_proc.stdout)
            self.assertFalse(missing_key_payload["verified"])
            self.assertTrue(
                any("no signing key was provided" in error for error in missing_key_payload["errors"])
            )

            verify_with_key_cmd = verify_cmd + ["--signing-key", "integration-secret"]
            verify_with_key_proc = subprocess.run(
                verify_with_key_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                verify_with_key_proc.returncode, 0, msg=verify_with_key_proc.stdout + verify_with_key_proc.stderr
            )
            verify_with_key_payload = json.loads(verify_with_key_proc.stdout)
            self.assertTrue(verify_with_key_payload["verified"])
            self.assertTrue(verify_with_key_payload["checks"]["signature"]["present"])
            self.assertTrue(verify_with_key_payload["checks"]["signature"]["verified"])


if __name__ == "__main__":
    unittest.main()

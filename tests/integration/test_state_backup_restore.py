import asyncio
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "eap_state_backup.py"


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


class StateBackupRestoreIntegrationTest(unittest.TestCase):
    def _build_fixture_state_db(self, db_path: Path) -> str:
        state_manager = StateManager(db_path=str(db_path))
        registry = ToolRegistry()
        registry.register("echo_tool", _echo_tool, TOOL_SCHEMA)
        executor = AsyncLocalExecutor(state_manager, registry)

        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="echo_tool", arguments={"value": "ok"})]
        )
        result = asyncio.run(executor.execute_macro(macro))
        run_id = str(result["metadata"]["execution_run_id"])
        state_manager.store_execution_diagnostics(
            run_id,
            {
                "root_failure": {"error_type": "none", "message": ""},
                "actor_metadata": {
                    "owner_actor_id": "integration-test",
                    "policy_profile": "strict",
                    "operation": "runs.execute",
                },
            },
        )
        return run_id

    def test_backup_then_restore_drill_succeeds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-state-backup-") as temp_dir:
            temp_root = Path(temp_dir)
            source_db_path = temp_root / "source_state.db"
            expected_run_id = self._build_fixture_state_db(source_db_path)

            backup_root = temp_root / "backups"
            backup_cmd = [
                sys.executable,
                str(BACKUP_SCRIPT),
                "backup",
                "--db-path",
                str(source_db_path),
                "--output-root",
                str(backup_root),
                "--name",
                "fixture-backup",
            ]
            backup_proc = subprocess.run(
                backup_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(backup_proc.returncode, 0, msg=backup_proc.stdout + backup_proc.stderr)
            backup_payload = json.loads(backup_proc.stdout)
            backup_dir = Path(backup_payload["backup_dir"])
            self.assertTrue((backup_dir / "backup_manifest.json").exists())
            self.assertTrue((backup_dir / "backup_metadata.json").exists())
            self.assertTrue((backup_dir / "state" / "agent_state.db").exists())
            self.assertTrue((backup_dir / "diagnostics" / "telemetry" / "overview.json").exists())

            restore_target_path = temp_root / "restored_state.db"
            restore_target_path.write_text("placeholder", encoding="utf-8")
            restore_diagnostics_root = temp_root / "restored_diagnostics"
            restore_cmd = [
                sys.executable,
                str(BACKUP_SCRIPT),
                "restore",
                "--backup-dir",
                str(backup_dir),
                "--db-path",
                str(restore_target_path),
                "--force",
                "--diagnostics-output-dir",
                str(restore_diagnostics_root),
            ]
            restore_proc = subprocess.run(
                restore_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(restore_proc.returncode, 0, msg=restore_proc.stdout + restore_proc.stderr)
            restore_payload = json.loads(restore_proc.stdout)
            self.assertEqual(restore_payload["status"], "ok")

            rollback_path = restore_payload["rollback_backup_path"]
            self.assertIsNotNone(rollback_path)
            self.assertTrue(Path(rollback_path).exists())
            self.assertTrue(Path(restore_payload["report_path"]).exists())

            restored_diagnostics_path = Path(restore_payload["diagnostics_output_path"])
            self.assertTrue((restored_diagnostics_path / "telemetry" / "operator_report.md").exists())
            self.assertTrue((restored_diagnostics_path / "audit_bundle" / "manifest.json").exists())

            with sqlite3.connect(restore_target_path) as conn:
                run_row = conn.execute(
                    "SELECT run_id FROM execution_run_summaries ORDER BY completed_at_utc DESC LIMIT 1"
                ).fetchone()
                self.assertIsNotNone(run_row)
                self.assertEqual(run_row[0], expected_run_id)
                diagnostics_row = conn.execute(
                    "SELECT payload_json FROM execution_run_diagnostics WHERE run_id = ?",
                    (expected_run_id,),
                ).fetchone()
                self.assertIsNotNone(diagnostics_row)

    def test_restore_rejects_tampered_backup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-state-backup-tamper-") as temp_dir:
            temp_root = Path(temp_dir)
            source_db_path = temp_root / "source_state.db"
            self._build_fixture_state_db(source_db_path)

            backup_root = temp_root / "backups"
            backup_cmd = [
                sys.executable,
                str(BACKUP_SCRIPT),
                "backup",
                "--db-path",
                str(source_db_path),
                "--output-root",
                str(backup_root),
                "--name",
                "tamper-backup",
            ]
            backup_proc = subprocess.run(
                backup_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(backup_proc.returncode, 0, msg=backup_proc.stdout + backup_proc.stderr)
            backup_payload = json.loads(backup_proc.stdout)
            backup_dir = Path(backup_payload["backup_dir"])

            trace_path = backup_dir / "diagnostics" / "audit_bundle" / "trace_events.json"
            trace_path.write_text(trace_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            restore_cmd = [
                sys.executable,
                str(BACKUP_SCRIPT),
                "restore",
                "--backup-dir",
                str(backup_dir),
                "--db-path",
                str(temp_root / "restored_state.db"),
            ]
            restore_proc = subprocess.run(
                restore_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(restore_proc.returncode, 1, msg=restore_proc.stdout + restore_proc.stderr)
            restore_payload = json.loads(restore_proc.stdout)
            self.assertEqual(restore_payload["status"], "error")
            self.assertIn("verification failed", restore_payload["reason"])
            self.assertTrue(
                any("file hash mismatch" in error for error in restore_payload["verification"]["errors"])
            )


if __name__ == "__main__":
    unittest.main()

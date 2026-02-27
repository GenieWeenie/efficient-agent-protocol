"""Integration tests verifying deterministic upgrade from v0.1.8 baseline."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from protocol.migrations import LATEST_SCHEMA_VERSION, apply_sqlite_migrations
from protocol.state_manager import StateManager
from tests.fixtures.baseline_state_builder import build_baseline_state_db


class UpgradeFromBaselineTest(unittest.TestCase):
    """Prove that a v0.1.8-baseline state DB upgrades safely to current."""

    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-upgrade-", suffix=".db")
        os.close(fd)
        os.remove(self.db_path)
        self.meta = build_baseline_state_db(self.db_path)

    def tearDown(self) -> None:
        for path in (self.db_path, self.db_path + ".bak"):
            if os.path.exists(path):
                os.remove(path)

    def test_baseline_schema_at_expected_version(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        self.assertEqual(row[0], 5)

    def test_migration_application_is_idempotent(self) -> None:
        first = apply_sqlite_migrations(self.db_path)
        self.assertEqual(first["final_version"], LATEST_SCHEMA_VERSION)

        second = apply_sqlite_migrations(self.db_path)
        self.assertEqual(second["applied_versions"], [])
        self.assertEqual(second["final_version"], LATEST_SCHEMA_VERSION)

    def test_all_required_tables_present_after_upgrade(self) -> None:
        apply_sqlite_migrations(self.db_path)
        required = {
            "state_store",
            "execution_trace_events",
            "execution_run_summaries",
            "execution_run_checkpoints",
            "execution_run_diagnostics",
            "conversation_sessions",
            "conversation_turns",
            "schema_migrations",
        }
        with sqlite3.connect(self.db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertTrue(required.issubset(tables), f"Missing: {required - tables}")

    def test_data_preserved_through_upgrade(self) -> None:
        apply_sqlite_migrations(self.db_path)
        with sqlite3.connect(self.db_path) as conn:
            run_count = conn.execute("SELECT COUNT(*) FROM execution_run_summaries").fetchone()[0]
            self.assertEqual(run_count, len(self.meta["run_ids"]))

            ptr_count = conn.execute("SELECT COUNT(*) FROM state_store").fetchone()[0]
            self.assertEqual(ptr_count, len(self.meta["pointer_ids"]))

            event_count = conn.execute("SELECT COUNT(*) FROM execution_trace_events").fetchone()[0]
            self.assertEqual(event_count, self.meta["num_trace_events"])

            session_count = conn.execute("SELECT COUNT(*) FROM conversation_sessions").fetchone()[0]
            self.assertEqual(session_count, len(self.meta["session_ids"]))

            turn_count = conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0]
            self.assertEqual(turn_count, self.meta["num_turns"])

    def test_pointer_data_integrity_after_upgrade(self) -> None:
        apply_sqlite_migrations(self.db_path)
        with sqlite3.connect(self.db_path) as conn:
            for pid in self.meta["pointer_ids"]:
                row = conn.execute(
                    "SELECT raw_data, summary FROM state_store WHERE pointer_id = ?",
                    (pid,),
                ).fetchone()
                self.assertIsNotNone(row, f"Pointer {pid} missing after upgrade")
                payload = json.loads(row[0])
                self.assertIn("value", payload)

    def test_state_manager_operates_on_upgraded_db(self) -> None:
        apply_sqlite_migrations(self.db_path)
        sm = StateManager(db_path=self.db_path)

        first_ptr = self.meta["pointer_ids"][0]
        raw = sm.pointer_store.retrieve_pointer(first_ptr)
        self.assertIsNotNone(raw)

        pointers = sm.pointer_store.list_pointers(include_expired=True)
        self.assertGreaterEqual(len(pointers), len(self.meta["pointer_ids"]))

        first_run = self.meta["run_ids"][0]
        events = sm.list_trace_events(first_run)
        self.assertTrue(len(events) > 0, "Expected trace events for baseline run")

    def test_new_data_can_be_written_after_upgrade(self) -> None:
        apply_sqlite_migrations(self.db_path)
        sm = StateManager(db_path=self.db_path)

        result = sm.store_and_point(
            raw_data={"upgrade": True, "value": 42},
            summary="Post-upgrade pointer",
        )
        self.assertIn("pointer_id", result)

        retrieved = sm.pointer_store.retrieve_pointer(result["pointer_id"])
        self.assertIsNotNone(retrieved)

    def test_rollback_via_backup_preserves_data(self) -> None:
        backup_path = self.db_path + ".bak"
        shutil.copy2(self.db_path, backup_path)

        apply_sqlite_migrations(self.db_path)

        with sqlite3.connect(backup_path) as conn:
            run_count = conn.execute("SELECT COUNT(*) FROM execution_run_summaries").fetchone()[0]
        self.assertEqual(run_count, len(self.meta["run_ids"]))

        os.replace(backup_path, self.db_path)
        with sqlite3.connect(self.db_path) as conn:
            restored_count = conn.execute("SELECT COUNT(*) FROM execution_run_summaries").fetchone()[0]
        self.assertEqual(restored_count, len(self.meta["run_ids"]))

    def test_verification_script_passes(self) -> None:
        from scripts.verify_upgrade_from_baseline import run_verification

        result = run_verification()
        self.assertEqual(result["status"], "ok", json.dumps(result, indent=2))
        for check in result["checks"]:
            self.assertTrue(check["ok"], f"Check failed: {check}")


if __name__ == "__main__":
    unittest.main()

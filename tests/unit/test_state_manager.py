import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from eap.protocol import ExecutionTraceEvent, ExecutionTraceEventType, StateManager


class StateManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-state-", suffix=".db")
        os.close(fd)
        self.manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_store_and_retrieve(self) -> None:
        ptr = self.manager.store_and_point(raw_data="hello", summary="done")
        value = self.manager.retrieve(ptr["pointer_id"])
        self.assertEqual(value, "hello")
        self.assertIn("created_at_utc", ptr["metadata"])
        self.assertIsNone(ptr["metadata"]["ttl_seconds"])
        self.assertIsNone(ptr["metadata"]["expires_at_utc"])

    def test_missing_pointer_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.manager.retrieve("ptr_missing")

    def test_clear_all_recreates_store(self) -> None:
        self.manager.store_and_point(raw_data="hello", summary="done")
        self.manager.clear_all()
        self.manager.store_and_point(raw_data="world", summary="done")

    def test_append_and_list_trace_events(self) -> None:
        run_id = "run_state_test"
        self.manager.append_trace_event(
            ExecutionTraceEvent(
                run_id=run_id,
                step_id="step_1",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.QUEUED,
            )
        )
        self.manager.append_trace_event(
            ExecutionTraceEvent(
                run_id=run_id,
                step_id="step_1",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.COMPLETED,
                output_pointer_id="ptr_done",
                duration_ms=10.5,
            )
        )
        events = self.manager.list_trace_events(run_id)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, ExecutionTraceEventType.QUEUED)
        self.assertEqual(events[1].output_pointer_id, "ptr_done")

    def test_store_and_get_execution_summary(self) -> None:
        self.manager.store_execution_summary(
            run_id="run_summary",
            started_at_utc="2026-02-23T00:00:00+00:00",
            completed_at_utc="2026-02-23T00:00:01+00:00",
            total_steps=3,
            succeeded_steps=2,
            failed_steps=1,
            total_duration_ms=1000.0,
            final_pointer_id="ptr_final",
        )
        summary = self.manager.get_execution_summary("run_summary")
        self.assertEqual(summary["total_steps"], 3)
        self.assertEqual(summary["succeeded_steps"], 2)
        self.assertEqual(summary["failed_steps"], 1)
        self.assertEqual(summary["final_pointer_id"], "ptr_final")

    def test_upsert_and_get_run_checkpoint(self) -> None:
        self.manager.upsert_run_checkpoint(
            run_id="run_ckpt",
            started_at_utc="2026-02-23T00:00:00+00:00",
            status="active",
            macro_payload={"steps": [{"step_id": "s1", "tool_name": "echo", "arguments": {}}]},
            step_status={"s1": {"status": "ok", "pointer_id": "ptr_1"}},
            branch_decisions={"s1": ["s2"]},
            final_pointer_id="ptr_final",
        )
        checkpoint = self.manager.get_run_checkpoint("run_ckpt")
        self.assertEqual(checkpoint["run_id"], "run_ckpt")
        self.assertEqual(checkpoint["status"], "active")
        self.assertEqual(checkpoint["step_status"]["s1"]["pointer_id"], "ptr_1")
        self.assertEqual(checkpoint["branch_decisions"]["s1"], ["s2"])
        self.assertEqual(checkpoint["final_pointer_id"], "ptr_final")

    def test_list_run_checkpoints_filters_by_status(self) -> None:
        self.manager.upsert_run_checkpoint(
            run_id="run_active",
            started_at_utc="2026-02-23T00:00:00+00:00",
            status="active",
            macro_payload={"steps": []},
            step_status={},
            branch_decisions={},
        )
        self.manager.upsert_run_checkpoint(
            run_id="run_completed",
            started_at_utc="2026-02-23T00:00:00+00:00",
            status="completed",
            macro_payload={"steps": []},
            step_status={},
            branch_decisions={},
        )
        active = self.manager.list_run_checkpoints(status="active")
        completed = self.manager.list_run_checkpoints(status="completed")
        self.assertEqual([item["run_id"] for item in active], ["run_active"])
        self.assertEqual([item["run_id"] for item in completed], ["run_completed"])

    def test_store_pointer_with_ttl_persists_lifecycle_fields(self) -> None:
        ptr = self.manager.store_and_point(raw_data="hello", summary="done", ttl_seconds=60)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT created_at_utc, ttl_seconds, expires_at_utc
                FROM state_store
                WHERE pointer_id = ?
                """,
                (ptr["pointer_id"],),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], 60)
        self.assertIsNotNone(row[2])

    def test_invalid_ttl_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.store_and_point(raw_data="hello", summary="done", ttl_seconds=0)

    def test_state_store_schema_migration_adds_lifecycle_columns(self) -> None:
        fd, legacy_db_path = tempfile.mkstemp(prefix="eap-legacy-state-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(legacy_db_path) and os.remove(legacy_db_path))

        with sqlite3.connect(legacy_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE state_store (
                    pointer_id TEXT PRIMARY KEY,
                    raw_data TEXT,
                    summary TEXT,
                    metadata TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO state_store (pointer_id, raw_data, summary, metadata) VALUES (?, ?, ?, ?)",
                ("ptr_legacy", "raw", "summary", json.dumps({"size_bytes": 3})),
            )

        migrated = StateManager(db_path=legacy_db_path)
        migrated.retrieve("ptr_legacy")

        with sqlite3.connect(legacy_db_path) as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(state_store)").fetchall()
            }
            row = conn.execute(
                "SELECT created_at_utc, ttl_seconds, expires_at_utc FROM state_store WHERE pointer_id = ?",
                ("ptr_legacy",),
            ).fetchone()

        self.assertIn("created_at_utc", columns)
        self.assertIn("ttl_seconds", columns)
        self.assertIn("expires_at_utc", columns)
        self.assertIsNotNone(row[0])
        self.assertIsNone(row[1])
        self.assertIsNone(row[2])

    def test_list_expired_and_cleanup_pointers(self) -> None:
        permanent = self.manager.store_and_point(raw_data="permanent", summary="keep")
        expiring = self.manager.store_and_point(raw_data="expiring", summary="expire", ttl_seconds=60)

        created_at = datetime.fromisoformat(expiring["metadata"]["created_at_utc"]).astimezone(timezone.utc)
        future = (created_at + timedelta(seconds=61)).isoformat()

        expired_before = self.manager.list_expired_pointers(now_utc=future)
        self.assertEqual([item["pointer_id"] for item in expired_before], [expiring["pointer_id"]])

        report = self.manager.cleanup_expired_pointers(now_utc=future)
        self.assertEqual(report["deleted_count"], 1)
        self.assertEqual(report["deleted_pointer_ids"], [expiring["pointer_id"]])

        with self.assertRaises(KeyError):
            self.manager.retrieve(expiring["pointer_id"])
        self.assertEqual(self.manager.retrieve(permanent["pointer_id"]), "permanent")

    def test_delete_pointer_removes_record(self) -> None:
        pointer = self.manager.store_and_point(raw_data="x", summary="y")
        self.manager.delete_pointer(pointer["pointer_id"])
        with self.assertRaises(KeyError):
            self.manager.retrieve(pointer["pointer_id"])


if __name__ == "__main__":
    unittest.main()

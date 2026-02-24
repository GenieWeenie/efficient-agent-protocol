import os
import sqlite3
import tempfile
import unittest

from protocol.migrations import LATEST_SCHEMA_VERSION, apply_sqlite_migrations, pending_migrations


def _create_legacy_schema(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_trace_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                resolved_arguments TEXT,
                input_pointer_ids TEXT,
                output_pointer_id TEXT,
                duration_ms REAL,
                retry_delay_seconds REAL,
                error_payload TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_run_summaries (
                run_id TEXT PRIMARY KEY,
                started_at_utc TEXT NOT NULL,
                completed_at_utc TEXT NOT NULL,
                total_steps INTEGER NOT NULL,
                succeeded_steps INTEGER NOT NULL,
                failed_steps INTEGER NOT NULL,
                total_duration_ms REAL NOT NULL,
                final_pointer_id TEXT
            )
            """
        )


class SqliteMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-migrations-", suffix=".db")
        os.close(fd)
        _create_legacy_schema(self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_pending_and_dry_run_migrations(self) -> None:
        pending = pending_migrations(self.db_path)
        self.assertEqual([step.version for step in pending], list(range(1, LATEST_SCHEMA_VERSION + 1)))

        result = apply_sqlite_migrations(self.db_path, dry_run=True)
        self.assertEqual(result["planned_versions"], [1, 2, 3, 4])
        self.assertEqual(result["applied_versions"], [])

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            self.assertIsNone(row)

    def test_apply_migrations_is_idempotent(self) -> None:
        first = apply_sqlite_migrations(self.db_path)
        self.assertEqual(first["applied_versions"], [1, 2, 3, 4])
        self.assertEqual(first["final_version"], LATEST_SCHEMA_VERSION)

        with sqlite3.connect(self.db_path) as conn:
            idx_rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='index'
                AND name IN (
                    'idx_execution_trace_events_step_id',
                    'idx_execution_run_summaries_completed_at',
                    'idx_execution_run_diagnostics_updated'
                )
                ORDER BY name
                """
            ).fetchall()
            self.assertEqual(
                [row[0] for row in idx_rows],
                [
                    "idx_execution_run_diagnostics_updated",
                    "idx_execution_run_summaries_completed_at",
                    "idx_execution_trace_events_step_id",
                ],
            )

            diagnostics_row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='execution_run_diagnostics'"
            ).fetchone()
            self.assertIsNotNone(diagnostics_row)

        second = apply_sqlite_migrations(self.db_path)
        self.assertEqual(second["applied_versions"], [])
        self.assertEqual(second["final_version"], LATEST_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()

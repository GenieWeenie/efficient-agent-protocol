"""Build a deterministic v0.1.8-baseline SQLite state database for upgrade tests.

The generated DB mirrors the schema and data patterns produced by a real
v0.1.8 ``StateManager`` + ``SQLitePointerStore`` instance *before* any
post-0.1.8 migrations are applied.  It is intentionally created at
schema-migration version **5** (the version shipped in 0.1.8) so the
upgrade verification tests can confirm that the current code handles
it correctly.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_BASELINE_PACKAGE_VERSION = "0.1.8"
_BASELINE_SCHEMA_VERSION = 5


def _now_utc() -> datetime:
    return datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def build_baseline_state_db(
    db_path: str | Path,
    *,
    num_runs: int = 3,
    num_pointers: int = 4,
    num_sessions: int = 2,
) -> dict[str, object]:
    """Create a v0.1.8-compatible state database with representative data.

    Returns a metadata dict describing what was inserted (useful for
    verification assertions).
    """
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _create_v018_schema(conn)
        _apply_v018_migrations(conn)
        meta = _seed_representative_data(
            conn,
            num_runs=num_runs,
            num_pointers=num_pointers,
            num_sessions=num_sessions,
        )
    finally:
        conn.close()
    return meta


def _create_v018_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS state_store (
            pointer_id TEXT PRIMARY KEY,
            raw_data TEXT,
            summary TEXT,
            metadata TEXT,
            created_at_utc TEXT,
            ttl_seconds INTEGER,
            expires_at_utc TEXT
        )
    """)
    conn.execute("""
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
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_trace_events_run_id "
        "ON execution_trace_events(run_id)"
    )
    conn.execute("""
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
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_run_checkpoints (
            run_id TEXT PRIMARY KEY,
            started_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            macro_payload TEXT NOT NULL,
            step_status_payload TEXT NOT NULL,
            branch_decisions_payload TEXT NOT NULL,
            final_pointer_id TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_execution_run_checkpoints_status
        ON execution_run_checkpoints(status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_execution_run_checkpoints_updated
        ON execution_run_checkpoints(updated_at_utc)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_run_diagnostics (
            run_id TEXT PRIMARY KEY,
            updated_at_utc TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_execution_run_diagnostics_updated
        ON execution_run_diagnostics(updated_at_utc)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            session_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            memory_strategy TEXT NOT NULL,
            window_turn_limit INTEGER,
            summary_text TEXT,
            metadata TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_turns (
            turn_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            pointer_ids TEXT,
            macro_run_id TEXT,
            metadata TEXT
        )
    """)
    conn.commit()


def _apply_v018_migrations(conn: sqlite3.Connection) -> None:
    """Record schema-migration rows for versions 1-5 (matching 0.1.8)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at_utc TEXT NOT NULL
        )
    """)
    applied_at = _now_utc().isoformat()
    migration_rows = [
        (1, "Create schema_migrations tracking table", applied_at),
        (2, "Add trace-event step_id index for faster diagnostics", applied_at),
        (3, "Add run-summary completion-time index for faster history queries", applied_at),
        (4, "Add execution run diagnostics table for telemetry exports", applied_at),
        (5, "Add actor metadata payload column to run checkpoints for governance", applied_at),
    ]
    for version, description, ts in migration_rows:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, description, applied_at_utc) "
            "VALUES (?, ?, ?)",
            (version, description, ts),
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_trace_events_step_id "
        "ON execution_trace_events(step_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_run_summaries_completed_at "
        "ON execution_run_summaries(completed_at_utc)"
    )
    # v5 added actor_metadata_payload; add column if not already present
    columns = {row[1] for row in conn.execute("PRAGMA table_info(execution_run_checkpoints)")}
    if "actor_metadata_payload" not in columns:
        conn.execute("ALTER TABLE execution_run_checkpoints ADD COLUMN actor_metadata_payload TEXT")
    conn.commit()


def _seed_representative_data(
    conn: sqlite3.Connection,
    *,
    num_runs: int,
    num_pointers: int,
    num_sessions: int,
) -> dict[str, object]:
    base_time = _now_utc()
    run_ids: list[str] = []
    pointer_ids: list[str] = []
    session_ids: list[str] = []

    for i in range(num_pointers):
        pid = f"ptr-baseline-{i:04d}"
        created = (base_time + timedelta(seconds=i)).isoformat()
        ttl: Optional[int] = 3600 if i % 2 == 0 else None
        expires: Optional[str] = (
            (base_time + timedelta(seconds=i + 3600)).isoformat() if ttl else None
        )
        conn.execute(
            "INSERT INTO state_store "
            "(pointer_id, raw_data, summary, metadata, created_at_utc, ttl_seconds, expires_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                pid,
                json.dumps({"value": f"baseline-payload-{i}"}),
                f"Baseline pointer {i}",
                json.dumps({"source": "baseline_fixture", "index": i}),
                created,
                ttl,
                expires,
            ),
        )
        pointer_ids.append(pid)

    for i in range(num_runs):
        run_id = f"run-baseline-{i:04d}"
        started = (base_time + timedelta(minutes=i * 10)).isoformat()
        completed = (base_time + timedelta(minutes=i * 10 + 5)).isoformat()
        conn.execute(
            "INSERT INTO execution_run_summaries "
            "(run_id, started_at_utc, completed_at_utc, total_steps, succeeded_steps, "
            "failed_steps, total_duration_ms, final_pointer_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, started, completed, 3, 3, 0, 5000.0 + i * 100, pointer_ids[0] if pointer_ids else None),
        )

        for step_idx in range(3):
            step_id = f"step-{run_id}-{step_idx}"
            conn.execute(
                "INSERT INTO execution_trace_events "
                "(run_id, step_id, tool_name, event_type, timestamp_utc, attempt, "
                "resolved_arguments, output_pointer_id, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    step_id,
                    f"tool_{step_idx}",
                    "completed",
                    (base_time + timedelta(minutes=i * 10, seconds=step_idx * 30)).isoformat(),
                    1,
                    json.dumps({"arg": f"value-{step_idx}"}),
                    pointer_ids[0] if pointer_ids else None,
                    1500.0 + step_idx * 100,
                ),
            )

        conn.execute(
            "INSERT INTO execution_run_checkpoints "
            "(run_id, started_at_utc, updated_at_utc, status, macro_payload, "
            "step_status_payload, branch_decisions_payload, final_pointer_id, "
            "actor_metadata_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                started,
                completed,
                "completed",
                json.dumps({"name": f"baseline-macro-{i}"}),
                json.dumps({"steps": [{"id": f"step-{j}", "status": "ok"} for j in range(3)]}),
                json.dumps({}),
                pointer_ids[0] if pointer_ids else None,
                json.dumps({"actor": "baseline-test-user"}),
            ),
        )

        conn.execute(
            "INSERT INTO execution_run_diagnostics (run_id, updated_at_utc, payload_json) "
            "VALUES (?, ?, ?)",
            (
                run_id,
                completed,
                json.dumps({"diagnostics": {"run_index": i, "source": "baseline"}}),
            ),
        )
        run_ids.append(run_id)

    for i in range(num_sessions):
        session_id = f"session-baseline-{i:04d}"
        created = (base_time + timedelta(hours=i)).isoformat()
        conn.execute(
            "INSERT INTO conversation_sessions "
            "(session_id, created_at_utc, updated_at_utc, memory_strategy, "
            "window_turn_limit, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                created,
                created,
                "sliding_window",
                20,
                json.dumps({"source": "baseline_fixture"}),
            ),
        )

        for t in range(3):
            turn_id = _uuid()
            role = "user" if t % 2 == 0 else "assistant"
            conn.execute(
                "INSERT INTO conversation_turns "
                "(turn_id, session_id, role, content, created_at_utc, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    turn_id,
                    session_id,
                    role,
                    f"Baseline turn {t} for session {i}",
                    (base_time + timedelta(hours=i, minutes=t)).isoformat(),
                    json.dumps({}),
                ),
            )
        session_ids.append(session_id)

    conn.commit()

    return {
        "baseline_version": _BASELINE_PACKAGE_VERSION,
        "schema_version": _BASELINE_SCHEMA_VERSION,
        "run_ids": run_ids,
        "pointer_ids": pointer_ids,
        "session_ids": session_ids,
        "num_trace_events": num_runs * 3,
        "num_turns": num_sessions * 3,
    }

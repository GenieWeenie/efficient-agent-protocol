from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MigrationStep:
    version: int
    description: str
    statements: List[str]


MIGRATIONS: List[MigrationStep] = [
    MigrationStep(
        version=1,
        description="Create schema_migrations tracking table",
        statements=[
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at_utc TEXT NOT NULL
            )
            """
        ],
    ),
    MigrationStep(
        version=2,
        description="Add trace-event step_id index for faster diagnostics",
        statements=[
            "CREATE INDEX IF NOT EXISTS idx_execution_trace_events_step_id ON execution_trace_events(step_id)"
        ],
    ),
    MigrationStep(
        version=3,
        description="Add run-summary completion-time index for faster history queries",
        statements=[
            "CREATE INDEX IF NOT EXISTS idx_execution_run_summaries_completed_at ON execution_run_summaries(completed_at_utc)"
        ],
    ),
    MigrationStep(
        version=4,
        description="Add execution run diagnostics table for telemetry exports",
        statements=[
            """
            CREATE TABLE IF NOT EXISTS execution_run_diagnostics (
                run_id TEXT PRIMARY KEY,
                updated_at_utc TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_execution_run_diagnostics_updated
            ON execution_run_diagnostics(updated_at_utc)
            """,
        ],
    ),
    MigrationStep(
        version=5,
        description="Add actor metadata payload column to run checkpoints for governance",
        statements=[
            """
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
            """,
            "ALTER TABLE execution_run_checkpoints ADD COLUMN actor_metadata_payload TEXT",
        ],
    ),
]


LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version if MIGRATIONS else 0


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at_utc TEXT NOT NULL
        )
        """
    )


def _current_schema_version(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "schema_migrations"):
        return 0
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
    return int(row[0]) if row else 0


def pending_migrations(
    db_path: str,
    target_version: Optional[int] = None,
) -> List[MigrationStep]:
    target = target_version if target_version is not None else LATEST_SCHEMA_VERSION
    if target < 0 or target > LATEST_SCHEMA_VERSION:
        raise ValueError(f"target_version must be between 0 and {LATEST_SCHEMA_VERSION}")

    with sqlite3.connect(db_path) as conn:
        current = _current_schema_version(conn)
    return [step for step in MIGRATIONS if current < step.version <= target]


def apply_sqlite_migrations(
    db_path: str,
    target_version: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, object]:
    target = target_version if target_version is not None else LATEST_SCHEMA_VERSION
    if target < 0 or target > LATEST_SCHEMA_VERSION:
        raise ValueError(f"target_version must be between 0 and {LATEST_SCHEMA_VERSION}")

    with sqlite3.connect(db_path) as conn:
        current = _current_schema_version(conn)
        planned = [step for step in MIGRATIONS if current < step.version <= target]

        if dry_run:
            return {
                "db_path": db_path,
                "dry_run": True,
                "current_version": current,
                "target_version": target,
                "planned_versions": [step.version for step in planned],
                "applied_versions": [],
            }

        _ensure_migration_table(conn)
        applied_versions: List[int] = []
        applied_at = datetime.now(timezone.utc).isoformat()

        for step in planned:
            for statement in step.statements:
                conn.execute(statement)
            conn.execute(
                """
                INSERT OR REPLACE INTO schema_migrations (version, description, applied_at_utc)
                VALUES (?, ?, ?)
                """,
                (step.version, step.description, applied_at),
            )
            applied_versions.append(step.version)

        final_version = _current_schema_version(conn)
        return {
            "db_path": db_path,
            "dry_run": False,
            "current_version": current,
            "target_version": target,
            "planned_versions": [step.version for step in planned],
            "applied_versions": applied_versions,
            "final_version": final_version,
        }

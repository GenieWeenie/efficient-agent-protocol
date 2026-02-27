#!/usr/bin/env python3
"""Verify that a v0.1.8-baseline state database upgrades cleanly to the
current package version.

Exit codes:
    0 — all checks pass
    1 — one or more checks failed
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from protocol.migrations import LATEST_SCHEMA_VERSION, apply_sqlite_migrations, pending_migrations
from tests.fixtures.baseline_state_builder import build_baseline_state_db


def _check_schema_version(db_path: str) -> Dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
        current = int(row[0]) if row else 0
    ok = current == LATEST_SCHEMA_VERSION
    return {
        "check": "schema_version",
        "ok": ok,
        "current": current,
        "expected": LATEST_SCHEMA_VERSION,
    }


def _check_required_tables(db_path: str) -> Dict[str, Any]:
    required = [
        "state_store",
        "execution_trace_events",
        "execution_run_summaries",
        "execution_run_checkpoints",
        "execution_run_diagnostics",
        "conversation_sessions",
        "conversation_turns",
        "schema_migrations",
    ]
    with sqlite3.connect(db_path) as conn:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = [t for t in required if t not in existing]
    return {
        "check": "required_tables",
        "ok": len(missing) == 0,
        "missing": missing,
    }


def _check_data_preservation(db_path: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    with sqlite3.connect(db_path) as conn:
        run_count = conn.execute("SELECT COUNT(*) FROM execution_run_summaries").fetchone()[0]
        if run_count != len(meta["run_ids"]):
            errors.append(f"run count: expected {len(meta['run_ids'])}, got {run_count}")

        ptr_count = conn.execute("SELECT COUNT(*) FROM state_store").fetchone()[0]
        if ptr_count != len(meta["pointer_ids"]):
            errors.append(f"pointer count: expected {len(meta['pointer_ids'])}, got {ptr_count}")

        event_count = conn.execute("SELECT COUNT(*) FROM execution_trace_events").fetchone()[0]
        if event_count != meta["num_trace_events"]:
            errors.append(f"trace event count: expected {meta['num_trace_events']}, got {event_count}")

        session_count = conn.execute("SELECT COUNT(*) FROM conversation_sessions").fetchone()[0]
        if session_count != len(meta["session_ids"]):
            errors.append(f"session count: expected {len(meta['session_ids'])}, got {session_count}")

        for run_id in meta["run_ids"]:
            row = conn.execute(
                "SELECT run_id FROM execution_run_summaries WHERE run_id = ?", (run_id,)
            ).fetchone()
            if not row:
                errors.append(f"missing run: {run_id}")

        for ptr_id in meta["pointer_ids"]:
            row = conn.execute(
                "SELECT pointer_id FROM state_store WHERE pointer_id = ?", (ptr_id,)
            ).fetchone()
            if not row:
                errors.append(f"missing pointer: {ptr_id}")

    return {
        "check": "data_preservation",
        "ok": len(errors) == 0,
        "errors": errors,
    }


def _check_state_manager_operations(db_path: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Verify StateManager can operate on the upgraded database."""
    errors: List[str] = []
    try:
        from protocol.state_manager import StateManager

        sm = StateManager(db_path=db_path)

        if meta["pointer_ids"]:
            first_ptr = meta["pointer_ids"][0]
            raw = sm.pointer_store.retrieve_pointer(first_ptr)
            if raw is None:
                errors.append(f"retrieve_pointer({first_ptr}) returned None")

        pointers = sm.pointer_store.list_pointers(include_expired=True)
        if len(pointers) < len(meta["pointer_ids"]):
            errors.append(
                f"list_pointers returned {len(pointers)}, expected >= {len(meta['pointer_ids'])}"
            )

        if meta["run_ids"]:
            first_run = meta["run_ids"][0]
            events = sm.list_trace_events(first_run)
            if not events:
                errors.append(f"list_trace_events({first_run}) returned empty")

    except Exception as exc:
        errors.append(f"StateManager operation failed: {exc}")

    return {
        "check": "state_manager_operations",
        "ok": len(errors) == 0,
        "errors": errors,
    }


def _check_rollback_path(db_path: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Verify backup/restore round-trip preserves data."""
    errors: List[str] = []
    backup_path = db_path + ".rollback_test.bak"
    try:
        shutil.copy2(db_path, backup_path)
        with sqlite3.connect(backup_path) as conn:
            run_count = conn.execute("SELECT COUNT(*) FROM execution_run_summaries").fetchone()[0]
            if run_count != len(meta["run_ids"]):
                errors.append(f"backup run count mismatch: {run_count}")
            ptr_count = conn.execute("SELECT COUNT(*) FROM state_store").fetchone()[0]
            if ptr_count != len(meta["pointer_ids"]):
                errors.append(f"backup pointer count mismatch: {ptr_count}")
    except Exception as exc:
        errors.append(f"rollback test failed: {exc}")
    finally:
        if os.path.exists(backup_path):
            os.remove(backup_path)

    return {
        "check": "rollback_path",
        "ok": len(errors) == 0,
        "errors": errors,
    }


def run_verification(db_path: str | None = None) -> Dict[str, Any]:
    """Run the full upgrade verification suite.

    If *db_path* is ``None``, a temporary baseline database is created.
    """
    created_temp = False
    if db_path is None:
        fd, db_path = tempfile.mkstemp(prefix="eap-upgrade-verify-", suffix=".db")
        os.close(fd)
        os.remove(db_path)
        created_temp = True

    try:
        meta = build_baseline_state_db(db_path)

        migration_result = apply_sqlite_migrations(db_path)

        checks: List[Dict[str, Any]] = [
            _check_schema_version(db_path),
            _check_required_tables(db_path),
            _check_data_preservation(db_path, meta),
            _check_state_manager_operations(db_path, meta),
            _check_rollback_path(db_path, meta),
        ]

        all_ok = all(c["ok"] for c in checks)
        return {
            "status": "ok" if all_ok else "fail",
            "baseline_version": meta["baseline_version"],
            "migration_result": migration_result,
            "checks": checks,
        }
    finally:
        if created_temp and os.path.exists(db_path):
            os.remove(db_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional path to an existing baseline DB. If omitted, a temp DB is generated.",
    )
    args = parser.parse_args(argv or sys.argv[1:])

    result = run_verification(db_path=args.db_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

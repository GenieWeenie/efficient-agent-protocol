#!/usr/bin/env python3
"""State health check and fragmentation analysis for EAP deployments.

Reports database size, table row counts, index health, WAL status,
and fragmentation metrics to help operators identify maintenance needs.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


REQUIRED_TABLES = (
    "execution_trace_events",
    "execution_run_summaries",
    "execution_run_checkpoints",
    "execution_run_diagnostics",
    "conversation_sessions",
    "conversation_turns",
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / (1024 * 1024), 3)


def _table_row_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for (table_name,) in tables:
        row = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()
        counts[table_name] = int(row[0]) if row else 0
    return counts


def _index_info(conn: sqlite3.Connection) -> List[Dict[str, str]]:
    rows = conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name"
    ).fetchall()
    return [{"index_name": row[0], "table_name": row[1]} for row in rows]


def _pragma_value(conn: sqlite3.Connection, pragma: str) -> str:
    row = conn.execute(f"PRAGMA {pragma}").fetchone()
    return str(row[0]) if row else "unknown"


def _fragmentation_estimate(conn: sqlite3.Connection) -> Dict[str, Any]:
    page_count = int(_pragma_value(conn, "page_count"))
    freelist_count = int(_pragma_value(conn, "freelist_count"))
    page_size = int(_pragma_value(conn, "page_size"))
    total_bytes = page_count * page_size
    free_bytes = freelist_count * page_size
    fragmentation_pct = round((freelist_count / page_count * 100) if page_count > 0 else 0.0, 2)
    return {
        "page_count": page_count,
        "freelist_count": freelist_count,
        "page_size_bytes": page_size,
        "total_size_bytes": total_bytes,
        "free_space_bytes": free_bytes,
        "fragmentation_percent": fragmentation_pct,
        "vacuum_recommended": fragmentation_pct > 10.0,
    }


def _check_missing_tables(conn: sqlite3.Connection) -> List[str]:
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    return [t for t in REQUIRED_TABLES if t not in existing]


def run_healthcheck(db_path: str, verbose: bool = False) -> Dict[str, Any]:
    path = Path(db_path).resolve()
    report: Dict[str, Any] = {
        "generated_at_utc": _now_utc_iso(),
        "db_path": str(path),
        "db_exists": path.exists(),
    }

    if not path.exists():
        report["status"] = "error"
        report["error"] = f"Database file not found: {path}"
        return report

    report["db_size_mb"] = _file_size_mb(path)

    wal_path = Path(f"{path}-wal")
    shm_path = Path(f"{path}-shm")
    report["wal_file_exists"] = wal_path.exists()
    report["wal_size_mb"] = _file_size_mb(wal_path)

    with sqlite3.connect(str(path)) as conn:
        report["journal_mode"] = _pragma_value(conn, "journal_mode")
        report["synchronous"] = _pragma_value(conn, "synchronous")

        missing = _check_missing_tables(conn)
        report["missing_tables"] = missing
        if missing:
            report["status"] = "degraded"
            report["warning"] = f"Missing required tables: {missing}"
        else:
            report["status"] = "healthy"

        report["table_row_counts"] = _table_row_counts(conn)
        report["indexes"] = _index_info(conn)
        report["fragmentation"] = _fragmentation_estimate(conn)

        if verbose:
            integrity = conn.execute("PRAGMA integrity_check(1)").fetchone()
            report["integrity_check"] = str(integrity[0]) if integrity else "unknown"

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run state database health check and fragmentation analysis."
    )
    parser.add_argument(
        "--db-path",
        default="agent_state.db",
        help="Path to the SQLite state database (default: agent_state.db).",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Write health report JSON to this path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include additional checks (integrity check).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_healthcheck(db_path=args.db_path, verbose=args.verbose)

    report_json = json.dumps(report, indent=2, sort_keys=True)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_json + "\n", encoding="utf-8")
        print(f"[healthcheck] Wrote report to {output_path}")

    print(report_json)

    if report.get("status") == "error":
        return 1
    if report.get("fragmentation", {}).get("vacuum_recommended"):
        print(
            "[healthcheck] Warning: fragmentation > 10%. Consider running VACUUM on the state DB.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

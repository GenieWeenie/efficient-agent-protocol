#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from protocol.migrations import LATEST_SCHEMA_VERSION, apply_sqlite_migrations


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply SQLite state DB migrations for EAP.")
    parser.add_argument("--db-path", default="agent_state.db", help="Path to SQLite DB file.")
    parser.add_argument(
        "--target-version",
        type=int,
        default=LATEST_SCHEMA_VERSION,
        help=f"Target schema version (default: {LATEST_SCHEMA_VERSION}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show planned migrations without applying.")
    parser.add_argument("--backup", action="store_true", help="Create a .bak file before applying migrations.")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        parser.error(f"DB file not found: {db_path}")

    if args.backup and not args.dry_run:
        backup_path = db_path.with_suffix(db_path.suffix + ".bak")
        shutil.copy2(db_path, backup_path)

    result = apply_sqlite_migrations(
        db_path=str(db_path),
        target_version=args.target_version,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

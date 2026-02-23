#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from protocol.state_manager import StateManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Export EAP operational metrics snapshot.")
    parser.add_argument("--db-path", default="agent_state.db", help="Path to SQLite DB file.")
    parser.add_argument(
        "--output",
        default="metrics/latest.json",
        help="Output path for metrics JSON (default: metrics/latest.json).",
    )
    args = parser.parse_args()

    state_manager = StateManager(db_path=args.db_path)
    result = state_manager.export_operational_metrics(output_path=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

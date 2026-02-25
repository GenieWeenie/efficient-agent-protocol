#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eap.runtime.audit_bundle import build_manifest, sha256_file


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_load(value: Optional[str]) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _resolve_run_ids(
    conn: sqlite3.Connection,
    requested_run_ids: Sequence[str],
    limit_runs: int,
) -> List[str]:
    if requested_run_ids:
        normalized = [run_id.strip() for run_id in requested_run_ids if run_id and run_id.strip()]
        deduped = list(dict.fromkeys(normalized))
        if not deduped:
            raise ValueError("At least one non-empty run ID is required when using --run-id.")
        placeholders = ",".join("?" for _ in deduped)
        rows = conn.execute(
            f"""
            SELECT run_id
            FROM execution_run_summaries
            WHERE run_id IN ({placeholders})
            """,
            tuple(deduped),
        ).fetchall()
        found = {row[0] for row in rows}
        missing = [run_id for run_id in deduped if run_id not in found]
        if missing:
            raise ValueError(f"Unknown run IDs: {missing}")
        return deduped

    rows = conn.execute(
        """
        SELECT run_id
        FROM execution_run_summaries
        ORDER BY completed_at_utc DESC
        LIMIT ?
        """,
        (limit_runs,),
    ).fetchall()
    return [row[0] for row in rows]


def _load_run_summaries(conn: sqlite3.Connection, run_ids: Sequence[str]) -> List[Dict[str, Any]]:
    if not run_ids:
        return []
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        f"""
        SELECT run_id, started_at_utc, completed_at_utc, total_steps, succeeded_steps, failed_steps,
               total_duration_ms, final_pointer_id
        FROM execution_run_summaries
        WHERE run_id IN ({placeholders})
        ORDER BY completed_at_utc DESC
        """,
        tuple(run_ids),
    ).fetchall()
    return [
        {
            "run_id": row[0],
            "started_at_utc": row[1],
            "completed_at_utc": row[2],
            "total_steps": int(row[3]),
            "succeeded_steps": int(row[4]),
            "failed_steps": int(row[5]),
            "total_duration_ms": float(row[6]),
            "final_pointer_id": row[7],
        }
        for row in rows
    ]


def _load_trace_events(conn: sqlite3.Connection, run_ids: Sequence[str]) -> List[Dict[str, Any]]:
    if not run_ids:
        return []
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        f"""
        SELECT event_id, run_id, step_id, tool_name, event_type, timestamp_utc, attempt,
               resolved_arguments, input_pointer_ids, output_pointer_id, duration_ms,
               retry_delay_seconds, error_payload
        FROM execution_trace_events
        WHERE run_id IN ({placeholders})
        ORDER BY event_id ASC
        """,
        tuple(run_ids),
    ).fetchall()
    payload: List[Dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "event_id": int(row[0]),
                "run_id": row[1],
                "step_id": row[2],
                "tool_name": row[3],
                "event_type": row[4],
                "timestamp_utc": row[5],
                "attempt": int(row[6]),
                "resolved_arguments": _safe_json_load(row[7]),
                "input_pointer_ids": _safe_json_load(row[8]),
                "output_pointer_id": row[9],
                "duration_ms": float(row[10]) if row[10] is not None else None,
                "retry_delay_seconds": float(row[11]) if row[11] is not None else None,
                "error_payload": _safe_json_load(row[12]),
            }
        )
    return payload


def _load_run_diagnostics(conn: sqlite3.Connection, run_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        f"""
        SELECT run_id, updated_at_utc, payload_json
        FROM execution_run_diagnostics
        WHERE run_id IN ({placeholders})
        ORDER BY updated_at_utc DESC
        """,
        tuple(run_ids),
    ).fetchall()
    payload: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        run_id = row[0]
        if run_id in payload:
            continue
        diagnostics_payload = _safe_json_load(row[2])
        payload[run_id] = {
            "updated_at_utc": row[1],
            "payload": diagnostics_payload if isinstance(diagnostics_payload, dict) else {},
        }
    return payload


def _load_run_checkpoints(conn: sqlite3.Connection, run_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        f"""
        SELECT run_id, started_at_utc, updated_at_utc, status, final_pointer_id, actor_metadata_payload
        FROM execution_run_checkpoints
        WHERE run_id IN ({placeholders})
        ORDER BY updated_at_utc DESC
        """,
        tuple(run_ids),
    ).fetchall()
    payload: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        run_id = row[0]
        actor_payload = _safe_json_load(row[5])
        payload[run_id] = {
            "started_at_utc": row[1],
            "updated_at_utc": row[2],
            "status": row[3],
            "final_pointer_id": row[4],
            "actor_metadata": actor_payload if isinstance(actor_payload, dict) else {},
        }
    return payload


def _build_governance_context(
    *,
    db_path: str,
    run_ids: Sequence[str],
    checkpoints: Dict[str, Dict[str, Any]],
    diagnostics: Dict[str, Dict[str, Any]],
    generated_at_utc: str,
) -> Dict[str, Any]:
    actor_by_run: Dict[str, Dict[str, Any]] = {}
    policy_profile_counts: Dict[str, int] = {}
    operation_counts: Dict[str, int] = {}
    for run_id in run_ids:
        checkpoint_actor = checkpoints.get(run_id, {}).get("actor_metadata")
        diagnostics_actor = diagnostics.get(run_id, {}).get("payload", {}).get("actor_metadata")
        actor_metadata = checkpoint_actor if isinstance(checkpoint_actor, dict) and checkpoint_actor else {}
        if not actor_metadata and isinstance(diagnostics_actor, dict):
            actor_metadata = diagnostics_actor
        actor_by_run[run_id] = actor_metadata

        policy_profile = actor_metadata.get("policy_profile")
        if isinstance(policy_profile, str) and policy_profile.strip():
            key = policy_profile.strip()
            policy_profile_counts[key] = policy_profile_counts.get(key, 0) + 1
        operation = actor_metadata.get("operation")
        if isinstance(operation, str) and operation.strip():
            op = operation.strip()
            operation_counts[op] = operation_counts.get(op, 0) + 1

    return {
        "chain_of_custody": {
            "generated_at_utc": generated_at_utc,
            "source_db_path": str(Path(db_path).resolve()),
            "source_hostname": platform.node(),
            "python_version": platform.python_version(),
            "exporter": "scripts/export_audit_bundle.py",
            "hash_algorithm": "sha256",
            "manifest_verification_required": True,
        },
        "retention_reference": "docs/remote_ops_governance.md#retention-baseline",
        "included_tables": [
            "execution_run_summaries",
            "execution_trace_events",
            "execution_run_checkpoints",
            "execution_run_diagnostics",
        ],
        "selected_run_count": len(run_ids),
        "selected_run_ids": list(run_ids),
        "policy_profile_counts": dict(sorted(policy_profile_counts.items())),
        "operation_counts": dict(sorted(operation_counts.items())),
        "actor_metadata_by_run": actor_by_run,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export an audit evidence bundle with manifest hashes and optional signature."
    )
    parser.add_argument("--db-path", default="agent_state.db", help="Path to SQLite state database.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/audit_bundle",
        help="Directory where bundle files are written.",
    )
    parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        help="Run ID to include (repeat flag to include multiple). Defaults to latest runs when omitted.",
    )
    parser.add_argument(
        "--limit-runs",
        type=int,
        default=100,
        help="Maximum recent runs when --run-id is omitted.",
    )
    parser.add_argument(
        "--signing-key",
        default=None,
        help="Optional HMAC signing key. Falls back to EAP_AUDIT_SIGNING_KEY.",
    )
    parser.add_argument(
        "--signer-key-id",
        default="local",
        help="Signer key identifier stored in manifest when signing is enabled.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit_runs <= 0:
        raise SystemExit("--limit-runs must be > 0")

    signing_key = args.signing_key or os.getenv("EAP_AUDIT_SIGNING_KEY")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(args.db_path) as conn:
        run_ids = _resolve_run_ids(conn, requested_run_ids=args.run_id, limit_runs=args.limit_runs)
        run_summaries = _load_run_summaries(conn, run_ids=run_ids)
        trace_events = _load_trace_events(conn, run_ids=run_ids)
        checkpoints = _load_run_checkpoints(conn, run_ids=run_ids)
        diagnostics = _load_run_diagnostics(conn, run_ids=run_ids)

    generated_at_utc = _now_utc_iso()
    governance_context = _build_governance_context(
        db_path=args.db_path,
        run_ids=run_ids,
        checkpoints=checkpoints,
        diagnostics=diagnostics,
        generated_at_utc=generated_at_utc,
    )

    artifacts: Dict[str, Any] = {
        "run_summaries.json": run_summaries,
        "trace_events.json": trace_events,
        "run_checkpoints.json": checkpoints,
        "run_diagnostics.json": diagnostics,
        "governance_context.json": governance_context,
    }
    for filename, payload in artifacts.items():
        (output_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    file_hashes = {
        filename: sha256_file(output_dir / filename)
        for filename in sorted(artifacts.keys())
    }
    manifest = build_manifest(
        generated_at_utc=generated_at_utc,
        db_path=str(Path(args.db_path).resolve()),
        run_ids=run_ids,
        file_hashes=file_hashes,
        signer_key_id=args.signer_key_id,
        signing_key=signing_key,
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = {
        "bundle_dir": str(output_dir.resolve()),
        "artifact_count": len(artifacts),
        "run_count": len(run_ids),
        "manifest_sha256": manifest["manifest_sha256"],
        "signed": "signature" in manifest,
        "manifest_path": str((output_dir / "manifest.json").resolve()),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

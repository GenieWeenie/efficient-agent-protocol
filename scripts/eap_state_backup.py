#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eap.runtime.audit_bundle import build_manifest, sha256_file, verify_bundle_manifest


BACKUP_MANIFEST_FILENAME = "backup_manifest.json"
BACKUP_METADATA_FILENAME = "backup_metadata.json"
DEFAULT_STATE_DB_FILENAME = "agent_state.db"
DEFAULT_BACKUP_ROOT = "artifacts/state_backups"
DEFAULT_RESTORE_DIAGNOSTICS_ROOT = "artifacts/restore/diagnostics"
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


def _utc_timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_exists(path: Path, *, path_label: str) -> None:
    if not path.exists():
        raise ValueError(f"{path_label} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{path_label} must be a file: {path}")


def _load_json(path: Path, *, path_label: str) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path_label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path_label} must be a JSON object: {path}")
    return payload


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _validate_state_db(path: Path) -> Dict[str, Any]:
    _ensure_exists(path, path_label="state DB")
    validation: Dict[str, Any] = {
        "db_path": str(path.resolve()),
        "required_tables": list(REQUIRED_TABLES),
        "missing_tables": [],
    }
    with sqlite3.connect(path) as conn:
        missing = [name for name in REQUIRED_TABLES if not _table_exists(conn, name)]
        validation["missing_tables"] = missing
        if missing:
            raise ValueError(f"state DB missing required tables: {missing}")
        run_count = conn.execute("SELECT COUNT(*) FROM execution_run_summaries").fetchone()
        diagnostics_count = conn.execute("SELECT COUNT(*) FROM execution_run_diagnostics").fetchone()
        validation["execution_run_count"] = int(run_count[0]) if run_count else 0
        validation["diagnostics_run_count"] = int(diagnostics_count[0]) if diagnostics_count else 0
    return validation


def _collect_table_counts(path: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    with sqlite3.connect(path) as conn:
        for table_name in REQUIRED_TABLES:
            row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            counts[table_name] = int(row[0]) if row else 0
    return counts


def _collect_run_ids(path: Path, *, limit: int) -> List[str]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            SELECT run_id
            FROM execution_run_summaries
            ORDER BY completed_at_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def _run_script(command: List[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "command failed: "
            + " ".join(command)
            + "\nstdout:\n"
            + completed.stdout
            + "\nstderr:\n"
            + completed.stderr
        )


def _iter_files(root: Path, *, excluded_names: Iterable[str]) -> List[Path]:
    excluded = set(excluded_names)
    files = [path for path in root.rglob("*") if path.is_file() and path.name not in excluded]
    files.sort(key=lambda path: path.as_posix())
    return files


def _relative_file_hashes(root: Path, *, excluded_names: Iterable[str]) -> Dict[str, str]:
    file_hashes: Dict[str, str] = {}
    for path in _iter_files(root, excluded_names=excluded_names):
        relpath = path.relative_to(root).as_posix()
        file_hashes[relpath] = sha256_file(path)
    return dict(sorted(file_hashes.items()))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _backup(args: argparse.Namespace) -> int:
    verbose = getattr(args, "verbose", False)
    dry_run = getattr(args, "dry_run", False)
    source_db_path = Path(args.db_path).resolve()
    _ensure_exists(source_db_path, path_label="source state DB")

    backup_root = Path(args.output_root).resolve()
    backup_name = args.name or f"state-backup-{_utc_timestamp_slug()}"
    backup_dir = backup_root / backup_name

    if verbose:
        print(f"[backup] Source DB: {source_db_path}")
        print(f"[backup] Backup destination: {backup_dir}")

    if dry_run:
        validation = _validate_state_db(source_db_path)
        table_counts = _collect_table_counts(source_db_path)
        print("[backup:dry-run] Would create backup with the following source data:")
        for table_name, count in sorted(table_counts.items()):
            print(f"[backup:dry-run]   {table_name}: {count} rows")
        print(f"[backup:dry-run] Backup would be written to: {backup_dir}")
        return 0

    backup_root.mkdir(parents=True, exist_ok=True)
    temp_dir = backup_root / f"{backup_name}.tmp"

    if backup_dir.exists() and not args.overwrite:
        raise ValueError(f"backup destination already exists: {backup_dir}")
    if backup_dir.exists() and args.overwrite:
        shutil.rmtree(backup_dir)
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        state_dir = temp_dir / "state"
        diagnostics_dir = temp_dir / "diagnostics"
        telemetry_dir = diagnostics_dir / "telemetry"
        audit_dir = diagnostics_dir / "audit_bundle"
        state_dir.mkdir(parents=True, exist_ok=True)
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        audit_dir.mkdir(parents=True, exist_ok=True)

        snapshot_db_path = state_dir / DEFAULT_STATE_DB_FILENAME
        # Use SQLite backup API instead of shutil.copy2 to safely handle WAL mode.
        # Plain file copy misses data in the -wal file, producing an incomplete snapshot.
        src_conn = sqlite3.connect(source_db_path)
        dst_conn = sqlite3.connect(snapshot_db_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
        if verbose:
            print("[backup] Copied state DB snapshot.")
        db_validation = _validate_state_db(snapshot_db_path)
        table_counts = _collect_table_counts(snapshot_db_path)
        run_ids = _collect_run_ids(snapshot_db_path, limit=max(1, int(args.run_id_limit)))
        if verbose:
            print(f"[backup] Validated snapshot: {sum(table_counts.values())} total rows across {len(table_counts)} tables.")

        _run_script(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "export_telemetry_pack.py"),
                "--db-path",
                str(snapshot_db_path),
                "--output-dir",
                str(telemetry_dir),
                "--limit-runs",
                str(max(1, int(args.telemetry_limit_runs))),
            ]
        )
        _run_script(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "export_audit_bundle.py"),
                "--db-path",
                str(snapshot_db_path),
                "--output-dir",
                str(audit_dir),
                "--limit-runs",
                str(max(1, int(args.audit_limit_runs))),
            ]
        )

        generated_at_utc = _now_utc_iso()
        backup_metadata = {
            "generated_at_utc": generated_at_utc,
            "backup_name": backup_name,
            "source_db_path": str(source_db_path),
            "snapshot_db_path": str(snapshot_db_path.relative_to(temp_dir).as_posix()),
            "table_counts": table_counts,
            "db_validation": db_validation,
            "run_id_count_in_manifest": len(run_ids),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        }
        _write_json(temp_dir / BACKUP_METADATA_FILENAME, backup_metadata)

        signing_key = args.signing_key or os.getenv("EAP_STATE_BACKUP_SIGNING_KEY")
        file_hashes = _relative_file_hashes(temp_dir, excluded_names=[BACKUP_MANIFEST_FILENAME])
        manifest = build_manifest(
            generated_at_utc=generated_at_utc,
            db_path=str(source_db_path),
            run_ids=run_ids,
            file_hashes=file_hashes,
            signer_key_id=args.signer_key_id,
            signing_key=signing_key,
        )
        _write_json(temp_dir / BACKUP_MANIFEST_FILENAME, manifest)

        verification = verify_bundle_manifest(
            bundle_dir=temp_dir,
            manifest=manifest,
            signing_key=signing_key,
            require_signature=bool(signing_key),
        )
        if not verification.verified:
            raise RuntimeError("backup manifest self-verification failed: " + "; ".join(verification.errors))

        temp_dir.replace(backup_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise

    payload = {
        "status": "ok",
        "operation": "backup",
        "backup_dir": str(backup_dir),
        "manifest_path": str(backup_dir / BACKUP_MANIFEST_FILENAME),
        "metadata_path": str(backup_dir / BACKUP_METADATA_FILENAME),
    }
    _print_json(payload)
    return 0


def _restore(args: argparse.Namespace) -> int:
    backup_dir = Path(args.backup_dir).resolve()
    if not backup_dir.exists() or not backup_dir.is_dir():
        raise ValueError(f"backup directory not found: {backup_dir}")

    manifest_path = backup_dir / BACKUP_MANIFEST_FILENAME
    metadata_path = backup_dir / BACKUP_METADATA_FILENAME
    manifest = _load_json(manifest_path, path_label="backup manifest")
    backup_metadata = _load_json(metadata_path, path_label="backup metadata")

    signing_key = args.signing_key or os.getenv("EAP_STATE_BACKUP_SIGNING_KEY")
    verification_details: Dict[str, Any] = {"verified": True, "errors": [], "checks": {}}
    if not args.skip_verify:
        result = verify_bundle_manifest(
            bundle_dir=backup_dir,
            manifest=manifest,
            signing_key=signing_key,
            require_signature=args.require_signature,
        )
        verification_details = {
            "verified": result.verified,
            "errors": result.errors,
            "checks": result.checks,
        }
        if not result.verified:
            _print_json(
                {
                    "status": "error",
                    "operation": "restore",
                    "reason": "backup verification failed",
                    "verification": verification_details,
                }
            )
            return 1

    snapshot_db_path = backup_dir / "state" / DEFAULT_STATE_DB_FILENAME
    snapshot_validation = _validate_state_db(snapshot_db_path)

    target_db_path = Path(args.db_path).resolve()
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_backup_path: Optional[Path] = None
    diagnostics_source = backup_dir / "diagnostics"
    diagnostics_output_path: Optional[Path] = None
    if diagnostics_source.exists() and diagnostics_source.is_dir() and not args.skip_diagnostics_restore:
        diagnostics_root = Path(args.diagnostics_output_dir).resolve()
        diagnostics_output_path = diagnostics_root / backup_dir.name
        if diagnostics_output_path.exists() and not args.force:
            raise ValueError(
                f"diagnostics destination already exists (use --force to replace): {diagnostics_output_path}"
            )

    if target_db_path.exists():
        if not args.force:
            raise ValueError(f"target DB already exists (use --force to replace): {target_db_path}")
        rollback_backup_path = target_db_path.with_name(
            f"{target_db_path.name}.pre_restore.{_utc_timestamp_slug()}.bak"
        )
        shutil.copy2(target_db_path, rollback_backup_path)

    restoring_path = target_db_path.with_name(f"{target_db_path.name}.restoring")
    if restoring_path.exists():
        restoring_path.unlink()
    shutil.copy2(snapshot_db_path, restoring_path)
    os.replace(restoring_path, target_db_path)
    restored_validation = _validate_state_db(target_db_path)

    if diagnostics_output_path is not None:
        if diagnostics_output_path.exists():
            shutil.rmtree(diagnostics_output_path)
        diagnostics_output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(diagnostics_source, diagnostics_output_path)

    report_payload = {
        "status": "ok",
        "operation": "restore",
        "backup_dir": str(backup_dir),
        "target_db_path": str(target_db_path),
        "rollback_backup_path": str(rollback_backup_path) if rollback_backup_path is not None else None,
        "diagnostics_output_path": str(diagnostics_output_path) if diagnostics_output_path is not None else None,
        "source_backup_metadata": backup_metadata,
        "snapshot_validation": snapshot_validation,
        "restored_validation": restored_validation,
        "verification": verification_details,
        "restored_at_utc": _now_utc_iso(),
    }

    if args.report_path:
        report_path = Path(args.report_path).resolve()
    else:
        report_root = Path(args.diagnostics_output_dir).resolve()
        report_path = report_root / f"restore_report_{_utc_timestamp_slug()}.json"
    _write_json(report_path, report_payload)
    report_payload["report_path"] = str(report_path)
    _print_json(report_payload)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backup and restore EAP runtime state + diagnostics with integrity verification."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a backup snapshot from a state DB.")
    backup.add_argument("--db-path", default=DEFAULT_STATE_DB_FILENAME, help="Source state DB path.")
    backup.add_argument(
        "--output-root",
        default=DEFAULT_BACKUP_ROOT,
        help="Directory where backup snapshots are written.",
    )
    backup.add_argument("--name", default=None, help="Optional backup directory name.")
    backup.add_argument("--overwrite", action="store_true", help="Allow replacing an existing backup name.")
    backup.add_argument(
        "--run-id-limit",
        type=int,
        default=5000,
        help="Maximum recent run IDs to include in the backup manifest metadata.",
    )
    backup.add_argument(
        "--telemetry-limit-runs",
        type=int,
        default=500,
        help="Maximum recent runs for telemetry export inside diagnostics snapshot.",
    )
    backup.add_argument(
        "--audit-limit-runs",
        type=int,
        default=500,
        help="Maximum recent runs for audit bundle export inside diagnostics snapshot.",
    )
    backup.add_argument(
        "--signing-key",
        default=None,
        help="Optional signing key. Falls back to EAP_STATE_BACKUP_SIGNING_KEY.",
    )
    backup.add_argument(
        "--signer-key-id",
        default="state-backup-local",
        help="Signer key identifier in the backup manifest when signing is enabled.",
    )
    backup.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress information during backup.",
    )
    backup.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and show what would be backed up without creating files.",
    )

    restore = subparsers.add_parser("restore", help="Restore a state DB from a backup snapshot.")
    restore.add_argument("--backup-dir", required=True, help="Backup directory created by the backup command.")
    restore.add_argument("--db-path", default=DEFAULT_STATE_DB_FILENAME, help="Restore target DB path.")
    restore.add_argument("--force", action="store_true", help="Allow replacing an existing target DB.")
    restore.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip backup manifest verification before restoring.",
    )
    restore.add_argument(
        "--require-signature",
        action="store_true",
        help="Require signature verification for backup manifest.",
    )
    restore.add_argument(
        "--signing-key",
        default=None,
        help="Optional signature verification key. Falls back to EAP_STATE_BACKUP_SIGNING_KEY.",
    )
    restore.add_argument(
        "--diagnostics-output-dir",
        default=DEFAULT_RESTORE_DIAGNOSTICS_ROOT,
        help="Destination root for restored diagnostics snapshot and default restore report path.",
    )
    restore.add_argument(
        "--skip-diagnostics-restore",
        action="store_true",
        help="Skip restoring diagnostics artifacts from the backup snapshot.",
    )
    restore.add_argument(
        "--report-path",
        default=None,
        help="Optional explicit path for restore report JSON.",
    )
    restore.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress information during restore.",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        if args.command == "backup":
            return _backup(args)
        if args.command == "restore":
            return _restore(args)
    except Exception as exc:
        _print_json(
            {
                "status": "error",
                "operation": args.command,
                "message": str(exc),
            }
        )
        return 1
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

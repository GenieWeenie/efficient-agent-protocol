# State Backup And Restore

This runbook defines the operator workflow for EAP state recovery (`EAP-098`).

## Scope

The backup snapshot includes:

- SQLite runtime state DB snapshot (`state/agent_state.db`)
- Diagnostics snapshot:
  - telemetry pack export (`diagnostics/telemetry/*`)
  - audit bundle export (`diagnostics/audit_bundle/*`)
- Integrity metadata:
  - `backup_metadata.json`
  - `backup_manifest.json` (hashes for all backup artifacts, optional signature)

## RPO And RTO Assumptions

- Target recovery point objective (RPO): <= 24 hours
  - take at least one backup per day, plus an additional backup before any migration or release.
- Target recovery time objective (RTO): <= 30 minutes
  - includes integrity verification, DB replacement, and post-restore validation.

These are operational defaults and can be tightened by increasing backup cadence and automating drill frequency.

## Commands

Create a backup:

```bash
python scripts/eap_state_backup.py backup \
  --db-path agent_state.db \
  --output-root artifacts/state_backups
```

Create a signed backup:

```bash
EAP_STATE_BACKUP_SIGNING_KEY="<secret>" \
python scripts/eap_state_backup.py backup \
  --db-path agent_state.db \
  --output-root artifacts/state_backups \
  --signer-key-id ops-key-2026
```

Restore from a backup:

```bash
python scripts/eap_state_backup.py restore \
  --backup-dir artifacts/state_backups/<backup-name> \
  --db-path agent_state.db \
  --force \
  --diagnostics-output-dir artifacts/restore/diagnostics
```

Require signature verification during restore:

```bash
EAP_STATE_BACKUP_SIGNING_KEY="<secret>" \
python scripts/eap_state_backup.py restore \
  --backup-dir artifacts/state_backups/<backup-name> \
  --db-path agent_state.db \
  --force \
  --require-signature
```

## Restore Drill Procedure

1. Create a fresh backup snapshot from the production-equivalent DB.
2. Restore the snapshot into a separate target DB path in a drill environment.
3. Confirm restored DB has expected run summary and diagnostics records.
4. Confirm restored diagnostics artifacts exist (`telemetry` + `audit_bundle`).
5. Record drill outcome and timings in the release/operations log.

## Failure Handling And Rollback

- Integrity failure (`backup verification failed`):
  - do not restore.
  - treat backup as compromised/corrupt and select a different backup snapshot.
- Target DB already exists:
  - restore requires `--force`.
  - when `--force` is used, a rollback copy is written automatically:
    - `<db>.pre_restore.<timestamp>.bak`
- Post-restore validation failure:
  - replace the restored DB with the generated rollback copy.
  - re-run restore against a different backup snapshot.

## Artifacts

Restore writes a machine-readable report JSON:

- default path: `artifacts/restore/diagnostics/restore_report_<timestamp>.json`
- configurable via `--report-path`

The report includes:

- verification result (hash/signature checks)
- rollback backup path (if target DB was replaced)
- restored diagnostics path
- table-level validation details

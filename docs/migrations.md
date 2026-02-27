# Migrations

This document defines how EAP handles SQLite schema/state migrations safely.

## Policy

- Schema changes must be additive and backward compatible when possible.
- Every schema change requires:
  - a migration step in `protocol/migrations.py`
  - a migration test in `tests/unit/test_migrations.py`
  - release notes mention if user action is needed
- Do not mutate or delete historical migration versions once released.

## Runtime Behavior

- `StateManager` applies pending SQLite migrations on startup.
- Applied versions are tracked in `schema_migrations`.

## Manual Migration Script

Use the migration script for explicit control (including dry-run and backups):

```bash
python3 scripts/migrate_state_db.py --db-path agent_state.db --dry-run
python3 scripts/migrate_state_db.py --db-path agent_state.db --backup
```

## Rollback Guidance

- Prefer restoring from backup (`--backup` creates `.bak` file) for SQLite rollback.
- If rollback is required after a release:
  - stop writes
  - restore DB backup
  - deploy previous compatible application version

## Upgrade Verification

Before releasing a new major or minor version, the upgrade path from the
last stable baseline is validated automatically.

### Automated verification

CI runs ``scripts/verify_upgrade_from_baseline.py`` and the integration tests
in ``tests/integration/test_upgrade_from_baseline.py`` on every push.  The
suite:

1. Creates a v0.1.8-compatible state database from deterministic fixtures.
2. Applies any pending migrations.
3. Validates schema version, required tables, and data preservation.
4. Exercises ``StateManager`` operations on the upgraded database.
5. Confirms the rollback path (backup / restore) preserves data.

### Manual verification

```bash
# From the repository root:
PYTHONPATH=. python scripts/verify_upgrade_from_baseline.py

# Or run the integration tests directly:
PYTHONPATH=. python -m pytest -q tests/integration/test_upgrade_from_baseline.py
```

### Rollback procedure

1. **Before upgrading**, create a backup:
   ```bash
   python scripts/migrate_state_db.py --db-path agent_state.db --backup --dry-run
   python scripts/migrate_state_db.py --db-path agent_state.db --backup
   ```
2. **If rollback is required:**
   - Stop the application.
   - Restore the `.bak` file: `cp agent_state.db.bak agent_state.db`.
   - Deploy the previous compatible application version.
3. **For full state backup/restore** (including diagnostics and audit data):
   ```bash
   python scripts/eap_state_backup.py backup --db-path agent_state.db
   python scripts/eap_state_backup.py restore --backup-dir artifacts/state_backups/<name> --force
   ```

## Versioning

- Current schema version is managed by `LATEST_SCHEMA_VERSION` in `protocol/migrations.py`.
- Latest additive governance migration (`v5`) adds `actor_metadata_payload` to `execution_run_checkpoints`.
- This column supports run ownership and scoped multi-user access enforcement in remote runtime mode.

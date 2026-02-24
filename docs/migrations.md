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

## Versioning

- Current schema version is managed by `LATEST_SCHEMA_VERSION` in `protocol/migrations.py`.
- Latest additive governance migration (`v5`) adds `actor_metadata_payload` to `execution_run_checkpoints`.
- This column supports run ownership and scoped multi-user access enforcement in remote runtime mode.

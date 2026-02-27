# Upgrade Notes: 0.1.8 → 0.1.9 (v1 API Deprecation Sweep)

## Summary

This release finalises the public namespace stability for the upcoming `v1.0`
cut.  Legacy import paths are deprecated, unstable surfaces are documented, and
the runtime HTTP server is formally added to the v1 contract.

## Deprecated

### Legacy top-level namespaces

The bare `protocol`, `environment`, and `agent` import paths are deprecated.
They continue to work but now emit `DeprecationWarning` on attribute access.
These legacy paths will be **removed in v2.0**.

| Before | After |
| --- | --- |
| `from protocol import StateManager` | `from eap.protocol import StateManager` |
| `from environment import ToolRegistry` | `from eap.environment import ToolRegistry` |
| `from agent import AgentClient` | `from eap.agent import AgentClient` |

**Action required:** update your imports to the `eap.*` namespace to silence
the warnings and prepare for v2.0 removal.

## Added

### `eap.runtime` in v1 contract

`EAPRuntimeHTTPServer` is now formally part of the v1 contract surface and is
tracked by the contract lock and CI gate.

## Unstable surfaces documented

`eap.environment.tools` (and `environment.tools`) are explicitly marked as
**not part of the v1 contract**.  These bundled tool implementations are
convenience utilities whose signatures may change between minor releases.

## Breaking Changes

None.  All existing imports continue to work; deprecated paths emit warnings
but remain functional.

## State Database Migration

SQLite state databases created by v0.1.8 are fully compatible.  The
``StateManager`` applies any pending schema migrations automatically on
startup.

### Pre-upgrade checklist

1. Back up your state database:
   ```bash
   python scripts/migrate_state_db.py --db-path agent_state.db --backup --dry-run
   python scripts/migrate_state_db.py --db-path agent_state.db --backup
   ```
2. Verify the planned migrations (should be empty for 0.1.8 → 0.1.9):
   ```bash
   python scripts/migrate_state_db.py --db-path agent_state.db --dry-run
   ```

### Post-upgrade verification

```bash
# Contract gate
PYTHONPATH=. python scripts/check_v1_contract.py --skip-version-history-check

# Upgrade path verification (creates temp baseline DB and validates)
PYTHONPATH=. python scripts/verify_upgrade_from_baseline.py

# Full integration test suite
PYTHONPATH=. python -m pytest -q tests/integration/test_upgrade_from_baseline.py
```

### Rollback

If you need to revert after upgrading:

1. Stop the application.
2. Restore the backup: `cp agent_state.db.bak agent_state.db`
3. Deploy the previous package version (0.1.8).

For a full state restore including diagnostics and audit data:

```bash
python scripts/eap_state_backup.py restore \
  --backup-dir artifacts/state_backups/<name> \
  --force
```

## Suppressing Deprecation Warnings

To suppress deprecation warnings in test output while migrating imports:

```python
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^(protocol|environment|agent)\b")
```

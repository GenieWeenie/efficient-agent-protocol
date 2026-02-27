# Upgrade Notes: 0.1.9 → 1.0.0

## Scope

### What changed from 0.1.9

- Package version bumped from `0.1.9` to `1.0.0`.
- All stabilization checklist items are complete (see `docs/v1_stabilization_checklist.md`).
- V1 readiness gatepack passes all 9 gates (`scripts/v1_readiness_gatepack.py`).
- Release and maintainer runbooks finalized for v1 process.
- Release Drafter template aligned with `docs/release_notes_template.md` structure.
- No runtime behavior changes between `0.1.9` and `1.0.0`; this is a stability milestone.

### What is now guaranteed stable

The following are frozen and covered by contract tests (see `docs/v1_contract.md`):

- **Public APIs**: `eap.protocol`, `eap.environment`, `eap.agent`, `eap.runtime` exports.
- **Workflow schema**: `PersistedWorkflowGraph`, `WorkflowGraphNode`, `WorkflowGraphEdge`, `WorkflowEdgeKind` fields and validation.
- **Error payloads**: `ToolErrorPayload` envelope and allowed `error_type` values.
- **Settings surface**: all keys returned by `load_settings()`.
- **Pointer lifecycle**: TTL, expiry evaluation, listing, retrieval, deletion, cleanup semantics.
- **Observability**: structured log JSON schema, operational metrics schema, telemetry pack artifact keys, execution diagnostics payload keys.
- **Storage migrations**: upgrade path from `v0.1.8+` with rollback support.

## Added

- Unified V1 readiness gatepack (`scripts/v1_readiness_gatepack.py`) — one command to validate all 9 pre-release gates.
- `docs/v1_readiness_gates.md` — gate-to-evidence mapping.
- `docs/v1_go_no_go_checklist.md` — release candidate decision criteria.
- Contract tests for docs/README alignment (`tests/contract/test_docs_v1_alignment.py`).

## Changed

- README status updated from "Experimental (pre-1.0)" to "v1.0 Release Candidate".
- `STABILITY.md` rewritten to reflect v1 contract posture with stable/unstable surface boundaries.
- Release Drafter template aligned with `docs/release_notes_template.md` sections.
- Release runbook expanded with V1.0 Release Checklist and RC tag procedures.
- Maintainer runbook expanded with V1 Contract Maintenance guidance.

## Fixed

- Version references across README, docs, and STABILITY.md now consistent with `pyproject.toml`.

## Deprecated

### Legacy top-level namespaces (since 0.1.9)

The bare `protocol`, `environment`, and `agent` import paths are deprecated.
They continue to work but emit `DeprecationWarning` on attribute access.
These legacy paths will be **removed in v2.0**.

| Before | After |
| --- | --- |
| `from protocol import StateManager` | `from eap.protocol import StateManager` |
| `from environment import ToolRegistry` | `from eap.environment import ToolRegistry` |
| `from agent import AgentClient` | `from eap.agent import AgentClient` |

**Action required:** update your imports to the `eap.*` namespace to silence
the warnings and prepare for v2.0 removal.

### Unstable surfaces

`eap.environment.tools` (and `environment.tools`) are explicitly **not part of
the v1 contract**. Pin a specific package version if you depend on these
bundled tool implementations.

## Removed

None. All existing APIs continue to work.

## Breaking Changes

None. The `1.0.0` release is a stability milestone with no runtime behavior
changes from `0.1.9`. All existing imports, configurations, and state
databases continue to work without modification.

## Migration Actions

### Required code changes

- **Import paths**: migrate from legacy namespaces (`protocol`, `environment`, `agent`) to `eap.*` equivalents. Legacy paths still work but emit deprecation warnings.

### Required config changes

None. All environment variables and configuration keys are unchanged.

### Required data/schema migration commands

SQLite state databases created by `v0.1.8+` are fully compatible. The
`StateManager` applies any pending schema migrations automatically on startup.

Pre-upgrade backup:

```bash
python scripts/eap_state_backup.py backup \
  --db-path agent_state.db \
  --output-root artifacts/state_backups

python scripts/migrate_state_db.py --db-path agent_state.db --backup --dry-run
python scripts/migrate_state_db.py --db-path agent_state.db --backup
```

## Verification Steps

After upgrading to `1.0.0`, run these commands to validate runtime behavior:

```bash
# 1. V1 readiness gatepack (all 9 gates)
PYTHONPATH=. python scripts/v1_readiness_gatepack.py

# 2. Contract lock validation
PYTHONPATH=. python scripts/check_v1_contract.py --skip-version-history-check

# 3. Upgrade path verification (creates temp baseline DB and validates)
PYTHONPATH=. python scripts/verify_upgrade_from_baseline.py

# 4. Full test suite
PYTHONPATH=. python -m pytest -q

# 5. Contract tests
PYTHONPATH=. python -m pytest -q tests/contract/

# 6. Smoke workflow
python -m examples.01_minimal
```

## Rollback Guidance

### Safe downgrade path

1. Stop the application.
2. Restore the database backup:
   ```bash
   python scripts/eap_state_backup.py restore \
     --backup-dir artifacts/state_backups/<name> \
     --force
   ```
   Or manually: `cp agent_state.db.bak agent_state.db`
3. Install the previous package version:
   ```bash
   pip install efficient-agent-protocol==0.1.9
   ```

### Constraints

- Downgrading is safe because `1.0.0` introduces no schema changes relative to `0.1.9`.
- If data was written after upgrading, the rollback restores the pre-upgrade snapshot; any data written post-upgrade is lost.
- For production environments, always take a backup before upgrading.

## Suppressing Deprecation Warnings

To suppress deprecation warnings in test output while migrating imports:

```python
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^(protocol|environment|agent)\b")
```

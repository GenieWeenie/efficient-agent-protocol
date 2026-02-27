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

## Verification

After upgrading, run the contract gate to confirm alignment:

```bash
PYTHONPATH=. python scripts/check_v1_contract.py --skip-version-history-check
```

To suppress deprecation warnings in test output while migrating:

```python
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^(protocol|environment|agent)\b")
```

# Stability Policy

This project is in **v1.0 Release Candidate** status. Core APIs, workflow schema, configuration keys, and storage semantics are frozen per [`docs/v1_contract.md`](docs/v1_contract.md).

## Current Guarantees

- Python runtime requirement (`>=3.9`) is intentional and documented.
- CI must pass for merges to `main`.
- Tagged releases are used for published milestones.
- The v1 contract surface (`eap.protocol`, `eap.environment`, `eap.agent`, `eap.runtime`) is frozen and covered by contract tests.

## Stable (v1 Contract)

- Public Python APIs in `eap.protocol`, `eap.environment`, `eap.agent`, and `eap.runtime`.
- Workflow JSON shape and validation behavior (`PersistedWorkflowGraph`).
- Configuration keys and defaults (see `docs/v1_contract.md`).
- Pointer lifecycle semantics (TTL, expiry, cleanup).
- Structured log JSON schema, operational metrics schema, and telemetry pack artifacts.
- Storage schema and migration paths from `v0.1.8+`.

## Not Yet Stable (May Change)

- Legacy namespaces (`protocol.*`, `environment.*`, `agent.*`) — deprecated, will be removed in v2.0.
- `eap.environment.tools` — explicitly excluded from v1 contract.
- Internal modules not re-exported through `__all__`.

## Versioning Intent

- `0.x`: rapid iteration, breaking changes are allowed.
- `1.0`: stable contracts for core API, workflow schema, and config surface.
- Post-`1.0`: breaking changes only in major releases with deprecation notes.

## Deprecation Policy

- Deprecations are announced in release notes and emit `DeprecationWarning` at runtime.
- Deprecated behavior will remain for at least one minor release before removal.
- Legacy namespaces (`protocol`, `environment`, `agent`) are deprecated as of `v0.1.9` and will be removed in `v2.0`.

## Release Expectations

- Each release includes a changelog summary.
- Breaking changes are clearly labeled.

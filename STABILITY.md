# Stability Policy

This project is currently **pre-1.0 (experimental)**.

## Current Guarantees

- Python runtime requirement (`>=3.9`) is intentional and documented.
- CI must pass for merges to `main`.
- Tagged releases are used for published milestones.

## Not Yet Stable (May Change Without Notice)

- Public Python APIs in `eap.*`, `agent.*`, `environment.*`, and `protocol.*`
- Workflow JSON shape and validation behavior
- Configuration keys and defaults
- Storage schema details and migration paths

## Versioning Intent

- `0.x`: rapid iteration, breaking changes are allowed.
- `1.0`: stable contracts for core API, workflow schema, and config surface.
- Post-`1.0`: breaking changes only in major releases with deprecation notes.

## Deprecation Policy (Target for 1.0+)

- Deprecations will be announced in release notes.
- Deprecated behavior will remain for at least one minor release before removal.

## Release Expectations

- Each release includes a changelog summary.
- Breaking changes are clearly labeled.

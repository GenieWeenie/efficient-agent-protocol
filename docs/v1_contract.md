# V1 Contract Draft

This document defines the intended contract for `v1.0`.
Until `v1.0` is released, this is a target contract and may still evolve in `0.x`.

## V1.0 Scope

The `v1.0` goal is a stable local-first execution core with a stable public import surface for:

- Macro planning/validation models
- Dependency-aware local execution
- Pointer-backed state persistence
- Basic provider integration through `AgentClient`

## V1.0 Non-Goals

The following are explicitly out of scope for `v1.0` stability guarantees:

- Streamlit UI layout and UX details in `app.py`
- Internal module organization under non-`eap.*` namespaces
- Experimental plugin manifest fields not exported through `eap.environment`
- Advanced distributed coordination semantics beyond documented behavior

## Public API Freeze Candidates (for V1.0)

The symbols exported by these module entry points are the stability candidates:

- `eap.protocol`
- `eap.environment`
- `eap.agent`

The current candidate symbol list is the explicit `__all__` set in those files.
Additions are allowed in minor releases; removals/behavioral breaks are only allowed in major releases after `v1.0`.

## Workflow Schema Freeze Candidates (for V1.0)

For `PersistedWorkflowGraph` and related types, these fields are intended to be stable:

- `workflow_id`
- `version`
- `nodes`
- `edges`
- `created_at_utc`
- `updated_at_utc`
- `metadata`

For node and edge models, these fields are intended to be stable:

- Node: `node_id`, `step`, `label`, `position_x`, `position_y`
- Edge: `source_node_id`, `target_node_id`, `kind`

The validation guarantees in `docs/workflow_schema.md` are also intended to be part of the `v1.0` contract.

## Supported User Profile

This project is currently best for:

- Python developers building local tool-execution agents
- Teams that want pointer-backed state and execution traces
- Users comfortable with pre-1.0 iteration and explicit upgrade checks

This project is not yet ideal for:

- Teams needing strict long-term API stability today
- Non-technical users expecting no-code setup
- Regulated production environments requiring formal support SLAs

## Release Notes Contract (starting now)

Each release notes entry should include, when applicable:

- `Added`
- `Changed`
- `Fixed`
- `Deprecated`
- `Removed`
- `Breaking Changes`
- `Upgrade Notes`

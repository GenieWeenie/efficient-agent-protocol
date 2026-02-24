# V1 Compatibility Contract

This document defines the enforced compatibility surface that must remain stable
for `v1.0` consumers.

While the project is still `0.x`, this contract is validated by CI to prevent
accidental drift.

## Scope

The `v1.0` contract covers:

- Public Python entry-point exports in:
  - `eap.protocol`
  - `eap.environment`
  - `eap.agent`
- Workflow graph schema fields and enum values for:
  - `PersistedWorkflowGraph`
  - `WorkflowGraphNode`
  - `WorkflowGraphEdge`
  - `WorkflowEdgeKind`
- Tool error payload envelope (`ToolErrorPayload`) including allowed `error_type`
  values.
- Frozen runtime settings key surface used by `load_settings()`.
- SDK HTTP operation path set for TypeScript and Go clients.

The source-of-truth lock file is:

- `docs/v1_contract_lock.json`

## Non-Goals

The following remain out of scope for `v1.0` stability guarantees:

- Streamlit UI layout and UX details in `app.py`
- Internal module organization under non-`eap.*` namespaces
- Experimental plugin manifest fields not exported through `eap.environment`
- Advanced distributed coordination semantics beyond documented behavior

## Enforcement

CI enforces contract stability through:

- `scripts/check_v1_contract.py`
- `tests/contract/test_v1_contract_lock.py`
- `tests/unit/test_v1_contract_gate.py`

What fails CI:

1. Runtime surface differs from `docs/v1_contract_lock.json`.
2. Contract lock changes without an explicit package version bump.

This provides a measurable gate for compatibility changes before `v1.0`.

## Intentional Contract Changes

If you intentionally change the frozen contract surface:

1. Bump package version in `pyproject.toml`.
2. Regenerate lock:
   - `PYTHONPATH=. python scripts/check_v1_contract.py --write-lock`
3. Update this document and release notes.
4. Ensure CI passes with the new lock.

## Supported User Profile

Best fit:

- Python developers building local tool-execution agents.
- Teams that need deterministic execution traces and pointer-backed state.
- Users comfortable with explicit compatibility gates during pre-`1.0`.

Not ideal yet:

- Teams requiring long-term, SLA-backed support commitments.
- Non-technical users expecting no-code setup.
- Fully managed hosted-control-plane expectations.

## Release Notes Requirements

Every release must include, when applicable:

- `Added`
- `Changed`
- `Fixed`
- `Deprecated`
- `Removed`
- `Breaking Changes`
- `Upgrade Notes`

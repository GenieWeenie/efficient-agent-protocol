# V1 Stabilization Checklist and Upgrade Handoff

This checklist defines the required handoff criteria before shipping `v1.0`.

## Goal

Ship `v1.0` with a stable contract for core runtime APIs, workflow schema, and upgrade guidance for existing `0.x` adopters.

## Entry Criteria

- `main` CI/Security/CodeQL pipelines are green.
- Latest release workflow is green, including post-release install smoke checks.
- Open high-severity code scanning alerts: `0`.

## Stabilization Checklist

### API and Namespace Freeze

- [x] Freeze exported symbols in `eap.protocol`, `eap.environment`, and `eap.agent`.
- [x] Document all symbols considered `v1.0` contract surface.
- [ ] Identify and remove or deprecate unstable public entry points before tag cut.

### Workflow and Data Contract Freeze

- [x] Freeze `PersistedWorkflowGraph` required/optional fields and validation rules.
- [x] Freeze executor error payload contract (`validation_error`, `dependency_error`, `tool_execution_error`).
- [x] Freeze pointer lifecycle semantics (TTL and cleanup behavior).

### Configuration and Operational Defaults

- [x] Freeze required environment variables and defaults.
- [ ] Verify migration scripts and migration docs cover upgrade from latest `0.x`.
- [ ] Verify observability defaults (structured logs + metrics export) remain compatible.

### Reliability and Performance Gates

- [ ] Keep line/branch coverage gates passing in CI.
- [ ] Keep perf regression thresholds green (`tests/perf` upper bounds).
- [ ] Validate retry/timeout/dependency failure integration tests pass.

### Security and Supply Chain

- [ ] Dependency audit and secret scan pipelines green.
- [ ] Code scanning alerts triaged with high-severity baseline at zero.
- [ ] Release workflow publishes and validates package install from PyPI.

### Documentation and Operator Readiness

- [x] Update `docs/v1_contract.md` from draft to final `v1.0` contract.
- [ ] Ensure README quickstart and docs links are current.
- [ ] Confirm release runbook and maintainer runbook reflect final `v1.0` process.

## Upgrade Notes Handoff (Required Artifact)

For `v1.0`, publish an explicit upgrade handoff with these sections:

1. Scope:
   - What changed from latest `0.x`.
   - What is now guaranteed stable.
2. Breaking changes:
   - Removed/renamed symbols.
   - Behavior changes in validation/execution semantics.
3. Migration actions:
   - Required code changes.
   - Required config changes.
   - Required data/schema migration commands.
4. Verification steps:
   - Commands to validate runtime behavior after upgrade.
5. Rollback guidance:
   - Safe downgrade path and constraints.

Use `docs/release_notes_template.md` and ensure `Breaking Changes` + `Upgrade Notes` are fully populated.

## Sign-Off

- [ ] Engineering owner approval
- [ ] Release owner approval
- [ ] Documentation owner approval

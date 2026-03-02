# Maintainer Runbook

This runbook captures core maintainer operations to reduce bus factor.

## Daily / Routine

- Review open issues and PRs.
- Confirm CI, Security, and CodeQL workflows are healthy.
- Triage flaky test reports and release blockers.

## Triage Process

1. Confirm reproduction details.
2. Classify severity and scope.
3. Label issue (`bug`, `enhancement`, roadmap phase labels).
4. Link issue to a milestone/roadmap task.

## Incident Response

1. Acknowledge issue and post impact statement.
2. Reproduce and isolate root cause.
3. Land fix behind CI validation.
4. Publish release and post remediation note.

## Recovery Drills

- Run periodic state backup/restore drills using `docs/state_backup_restore.md`.
- Verify integrity checks and rollback path behavior at least once per release cycle.
- Capture drill timestamps and observed RPO/RTO in release notes or operations logs.

## Release Owner Checklist

- Follow `docs/release.md` (including the V1.0 Release Checklist for major releases).
- Validate release notes follow `docs/release_notes_template.md` structure.
- Verify post-release workflows are green.
- For v1.0+: confirm `docs/v1_stabilization_checklist.md` sign-off is complete.

## V1 Contract Maintenance

After the v1.0 release, the contract surface is frozen. Follow these rules:

### Adding to the Contract

- New symbols may be added to `eap.protocol`, `eap.environment`, `eap.agent`, or `eap.runtime` without a breaking change.
- Update `docs/v1_contract_lock.json` in the same PR and bump the minor version.
- CI enforces lock consistency via `scripts/check_v1_contract.py`.

### Removing or Changing Contract Surface

- Removing or renaming any frozen symbol, field, or behavior is a **breaking change**.
- Breaking changes require a **major version bump** (v2.0+).
- Emit `DeprecationWarning` for at least one minor release before removal.
- Document the change in `Breaking Changes` and `Upgrade Notes` in release notes.

### Handling Contract Test Failures

- If `tests/contract/` tests fail on a PR, the change likely violates the v1 contract.
- Evaluate whether the change is intentional (contract evolution) or accidental (regression).
- Intentional changes must follow the removal/change process above.

### Ongoing Gate Validation

- Run `PYTHONPATH=. python scripts/v1_readiness_gatepack.py` periodically to verify all gates remain green.
- The gatepack runs automatically in CI on every push (py3.11 job).
- Gate documentation: `docs/v1_readiness_gates.md`.

## Incident Scenarios and Mitigations

### Scenario 1: State DB corruption or missing tables

**Symptoms**: Errors like `OperationalError: no such table: execution_trace_events`, or runs fail to persist.

**Diagnosis**:
```bash
python scripts/eap_state_healthcheck.py --db-path agent_state.db --verbose
```

**Mitigation**:
1. Check the `missing_tables` field in the health report.
2. If tables are missing, run the migration script: `python scripts/migrate_state_db.py --db-path agent_state.db`
3. If the DB is corrupted (integrity check fails), restore from the most recent backup: `python scripts/eap_state_backup.py restore --backup-dir artifacts/state_backups/<latest> --force`
4. Collect a support bundle before restoring: `python scripts/eap_support_bundle.py --verbose`

### Scenario 2: High latency / executor saturation

**Symptoms**: Runs take significantly longer than baseline, queue depth grows, or rate-limit errors appear in logs.

**Diagnosis**:
```bash
python scripts/export_telemetry_pack.py --verbose --db-path agent_state.db
# Check artifacts/telemetry/saturation.json and latency_percentiles.json
```

**Mitigation**:
1. Review `saturation.json` — check `global_concurrency_wait_seconds` and `per_tool_concurrency_wait_seconds`.
2. If global concurrency is saturated, increase `EAP_EXECUTOR_MAX_CONCURRENCY`.
3. If a specific tool is the bottleneck, add per-tool limits: `EAP_EXECUTOR_PER_TOOL_LIMITS_JSON`.
4. Review retry policies — excessive retries amplify load. Reduce `max_attempts` or tighten `retryable_error_types`.
5. See `docs/performance_tuning.md` for detailed guidance.

### Scenario 3: Provider connectivity failures

**Symptoms**: `ConnectionError` or `TimeoutError` in agent logs, streaming falls back to non-stream mode.

**Diagnosis**:
```bash
python scripts/eap_doctor.py doctor --env-file .env --verbose
```

**Mitigation**:
1. Verify the provider endpoint is reachable: check `provider_connectivity` in doctor output.
2. If using a local model server (LM Studio, Ollama), confirm it is running and the port matches `EAP_BASE_URL`.
3. Increase `EAP_TIMEOUT_SECONDS` if the model is slow to respond.
4. If using the `responses` API mode, verify gateway SSE support. See `docs/streaming_compatibility.md`.

## Response Expectations

- First maintainer response target:
  - issues: within 3 business days
  - PRs: within 3 business days
- If blocked, post status update within 7 days.

## Credentials and Access

- Keep repository admin and package publish access documented and rotated.
- Prefer PyPI Trusted Publishing for stable releases (avoid long-lived PyPI tokens in GitHub secrets).
- Keep branch protection enabled on `main`.
- Ensure at least two maintainers have workflow/release access when team size allows.

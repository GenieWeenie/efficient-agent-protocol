# Troubleshooting

This guide covers common setup and runtime problems.

## Bootstrap Quickstart Issues

### `bootstrap_local.sh` reports unsupported platform
Cause:
- The bootstrap script targets macOS/Linux shells.

Fix:
- On Windows, use WSL2 and run:
  - `./scripts/bootstrap_local.sh`
- Or run manual setup from `README.md` Quickstart.

### Environment validation failed during bootstrap
Cause:
- Required keys in `.env` are missing/invalid.

Fix:
- Ensure `.env` includes:
  - `EAP_BASE_URL` with `http://` or `https://`
  - `EAP_MODEL`
  - `EAP_API_KEY`
- Re-run:
  - `./scripts/bootstrap_local.sh`

### Bootstrap fails with Python version error
Cause:
- Bootstrap supports Python `3.9` through `3.13`.

Fix:
- Check version:
  - `python3 --version`
- Use Python `3.11` or another `3.9-3.13` interpreter:
  - `./scripts/bootstrap_local.sh --python python3.11`

### Smoke workflow failed during bootstrap
Cause:
- Local Python environment is not installed correctly.

Fix:
- Re-run install manually to inspect errors:
  - `./scripts/bootstrap_local.sh --skip-env-validation`
- Or install explicitly:
  - `python3 -m pip install -e .`

## Doctor Command

Run doctor:
- `python scripts/eap_doctor.py doctor --env-file .env --output-json artifacts/doctor/diagnostics.json`

Exit code categories (bitmask):
- `1` = environment file errors (`env`)
- `2` = configuration parsing/loading errors (`config`)
- `4` = provider connectivity errors (`connectivity`)
- `8` = storage roundtrip errors (`storage`)
- `16` = local tool/runtime prerequisite errors (`tools`)

Examples:
- Exit code `5` means `env` + `connectivity` failures (`1 + 4`)
- Exit code `24` means `storage` + `tools` failures (`8 + 16`)

Doctor remediation map:
- `env`: regenerate `.env` with
  - `python scripts/eap_doctor.py init-env --output .env --force`
- `config`: review `docs/configuration.md` and resolve invalid field values
- `connectivity`: verify gateway host/port is reachable and base URLs are correct
- `storage`: ensure local filesystem write permissions for the configured DB path
- `tools`: install missing tools/runtime dependencies and rerun doctor

## Self-Hosted Stack Issues

### `docker compose` fails with missing `EAP_RUNTIME_BEARER_TOKEN`
Cause:
- The compose stack requires a runtime bearer token.

Fix:
- Create and configure the stack env file:
  - `cp deploy/self_hosted/.env.example deploy/self_hosted/.env`
  - set `EAP_RUNTIME_BEARER_TOKEN` in `deploy/self_hosted/.env`
- Restart:
  - `docker compose --env-file deploy/self_hosted/.env -f deploy/self_hosted/docker-compose.yml up --build -d`

### Runtime smoke fails with `401 unauthorized`
Cause:
- Smoke token does not match the runtime token in compose env.

Fix:
- Pass the exact configured token:
  - `python scripts/self_hosted_stack_smoke.py --base-url http://127.0.0.1:8080 --bearer-token "<runtime-token>"`

### Runtime API returns `403 forbidden` with missing scope message
Cause:
- Scoped auth is enabled and the caller token lacks the endpoint scope.

Fix:
- Ensure the token includes the required scope:
  - execute: `runs:execute`
  - resume: `runs:resume`
  - run inspect: `runs:read`
  - pointer summary: `pointers:read`
- For cross-run operations, include corresponding `*:any` scopes.
- See:
  - `docs/remote_ops_governance.md`

### Runtime service fails with `disallowed by profile` or `unknown template`
Cause:
- `--scoped-auth-config` token entry requests scopes not allowed by the selected policy profile
  or references a template name not defined for that profile.

Fix:
- Verify `policy_profile` is one of `strict`, `balanced`, `trusted`.
- Verify token `template` is one of `viewer`, `operator`, `auditor`, `admin`.
- For strict deployments, remove elevated scopes such as `runs:resume:any`.
- See:
  - `docs/remote_ops_governance.md`

### Runtime API returns `429 rate_limited`
Cause:
- Endpoint request count exceeded configured rate window for the actor.

Fix:
- Respect `Retry-After` response header before retrying.
- Raise operation limit in `--guardrails-config` if sustained load is expected.
- Verify traffic distribution is not funneled through one shared actor token.

### Runtime API returns `429 throttled`
Cause:
- Concurrency ceiling reached (`global_inflight`, operation inflight, or per-run resume limit).

Fix:
- Retry with backoff and jitter.
- Lower parallel caller fan-out.
- Increase concurrency limits in `--guardrails-config` after capacity validation.
- Review runtime logs for `[runtime:guardrail]` events to identify dominant limit type.

## Audit Bundle Verification Issues

### `verify_audit_bundle.py` fails with `file hash mismatch`
Cause:
- One or more exported artifacts changed after `manifest.json` was generated.

Fix:
- Re-export the bundle and avoid post-export modifications.
- Verify from a read-only copy:
  - `python scripts/verify_audit_bundle.py --bundle-dir artifacts/audit_bundle`

### `verify_audit_bundle.py` fails with `manifest is signed but no signing key was provided`
Cause:
- Bundle includes an HMAC signature but verifier key was not supplied.

Fix:
- Provide the same signing key used during export:
  - `python scripts/verify_audit_bundle.py --bundle-dir artifacts/audit_bundle --signing-key "$EAP_AUDIT_SIGNING_KEY"`
- Or inject the key via env:
  - `EAP_AUDIT_SIGNING_KEY=... python scripts/verify_audit_bundle.py --bundle-dir artifacts/audit_bundle`

### Need stronger trust for unsigned manifests
Cause:
- Unsigned manifests can prove file consistency but not origin authenticity by themselves.

Fix:
- Record `manifest_sha256` in an immutable system when exporting.
- Verify against that external digest:
  - `python scripts/verify_audit_bundle.py --bundle-dir artifacts/audit_bundle --expected-manifest-sha256 "<digest>"`
- Prefer signed export mode for high-assurance workflows.

### Operator UI is reachable but no runs appear
Cause:
- No workflow has executed yet, or runtime and UI are not sharing the same state volume.

Fix:
- Confirm smoke run succeeds first.
- Check both services mount `eap_state` and use `/var/lib/eap/agent_state.db`.
- View compose status:
  - `docker compose --env-file deploy/self_hosted/.env -f deploy/self_hosted/docker-compose.yml ps`

## Import Errors

### `ModuleNotFoundError: No module named 'eap'`
Cause:
- Running scripts directly from `examples/` without package path context.

Fix:
- Use module execution from repo root:
  - `python3 -m examples.01_minimal`
  - `python3 -m examples.02_multi_tool_dag`
  - `python3 -m examples.03_retry_and_recovery`
- Or install editable package:
  - `pip install -e .`

## Streamlit App Fails at Startup

### Base URL validation errors
Cause:
- `EAP_BASE_URL` or role-specific URL missing `http://` / `https://`.

Fix:
- Set valid URLs in environment:
  - `EAP_BASE_URL=http://localhost:1234`
  - `EAP_ARCHITECT_BASE_URL=...`
  - `EAP_AUDITOR_BASE_URL=...`

### Invalid timeout/temperature values
Cause:
- Non-numeric or out-of-range env values.

Fix:
- Timeout must be integer > 0.
- Temperature must be float >= 0.

## Provider Selection Errors

### `Unsupported provider: ...`
Cause:
- Unknown `provider_name` passed to `AgentClient`.

Fix:
- Use one of: `local`, `openai`, `anthropic`, `google`.
- Optionally set `fallback_provider_name`.

### API key errors for Anthropic/Google
Cause:
- `api_key` missing or set to `not-needed` for providers that require auth.

Fix:
- Supply a valid key when using `anthropic` or `google`.

### `OpenAI Responses API path is unavailable on this endpoint.`
Cause:
- `EAP_OPENAI_API_MODE=responses` is configured but the gateway does not expose `POST /v1/responses`.

Fix:
- Enable responses support on the gateway if available.
- Or switch back to chat completions mode:
  - `EAP_OPENAI_API_MODE=chat_completions`
  - role-specific: `EAP_ARCHITECT_OPENAI_API_MODE=chat_completions`

## Tool Execution Failures

### Validation errors before tool runs
Cause:
- Macro arguments don’t satisfy tool JSON schema.

Fix:
- Inspect schema in tool registry/manifest.
- Ensure required fields and types are correct.

### Dependency step failure (`dependency_error`)
Cause:
- A step references a failed upstream pointer.

Fix:
- Check execution trace for root failing step.
- Fix upstream tool call or retry policy.

## Retry Behavior Not Triggering

Cause:
- Exception type not listed in `RetryPolicy.retryable_error_types`.

Fix:
- Include expected exception class name (e.g., `RuntimeError`) in retry policy.

## Streaming Output Issues

### Responses mode stream returns no incremental tokens
Cause:
- Gateway may only emit final completion events, or may not emit SSE deltas for `responses` mode.

Fix:
- Verify gateway supports SSE streaming for `POST /v1/responses`.
- If only final events are emitted, EAP still returns final text chunks.
- For strict token-by-token streaming, prefer `chat_completions` mode on gateways with mature SSE behavior.

## Database / State Issues

### Pointer or session not found
Cause:
- Referencing IDs that were cleared or never created.

Fix:
- Verify IDs in UI tabs (`Pointer Vault`, `Execution Trace`).
- If needed, clear and re-run workflow.

### Need a clean slate
Fix:
- Use Streamlit sidebar button: `Clear All Data`.
- Or remove the SQLite DB file (`agent_state.db`) manually.

## Debugging Checklist

1. Run tests:
   - `python3 -m pytest -q`
2. Verify environment configuration:
   - `docs/configuration.md`
3. Reproduce with minimal example:
   - `python3 -m examples.01_minimal`
4. Inspect trace details in `Execution Trace` tab.

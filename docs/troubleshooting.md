# Troubleshooting

This guide covers common setup and runtime problems.

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

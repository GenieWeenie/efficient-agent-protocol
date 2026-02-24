# Configuration

EAP reads runtime configuration from environment variables. The app loads settings through `eap.protocol.load_settings()` at startup and fails fast if values are invalid.

## Quick Start

1. Copy `.env.example` to `.env` (or export vars in your shell).
2. Set provider/model values for architect and auditor roles.
3. Start app:
   - `streamlit run app.py`

## Variables

Global defaults:
- `EAP_BASE_URL`
- `EAP_MODEL`
- `EAP_API_KEY`
- `EAP_TIMEOUT_SECONDS`
- `EAP_TEMPERATURE`
- `EAP_OPENAI_API_MODE` (`chat_completions` or `responses`, default: `chat_completions`)
- `EAP_EXTRA_HEADERS_JSON` (optional JSON object of HTTP headers)

Role-specific overrides:
- `EAP_ARCHITECT_BASE_URL`
- `EAP_ARCHITECT_MODEL`
- `EAP_ARCHITECT_API_KEY`
- `EAP_ARCHITECT_TIMEOUT_SECONDS`
- `EAP_ARCHITECT_TEMPERATURE`
- `EAP_ARCHITECT_OPENAI_API_MODE` (`chat_completions` or `responses`)
- `EAP_ARCHITECT_EXTRA_HEADERS_JSON` (optional JSON object of HTTP headers)
- `EAP_AUDITOR_BASE_URL`
- `EAP_AUDITOR_MODEL`
- `EAP_AUDITOR_API_KEY`
- `EAP_AUDITOR_TIMEOUT_SECONDS`
- `EAP_AUDITOR_TEMPERATURE`
- `EAP_AUDITOR_OPENAI_API_MODE` (`chat_completions` or `responses`)
- `EAP_AUDITOR_EXTRA_HEADERS_JSON` (optional JSON object of HTTP headers)

Logging:
- `EAP_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `EAP_LOG_FORMAT` (`json` or `text`, default: `json`)
- `EAP_LOG_JSON` (legacy boolean override for JSON logs)

Executor concurrency/rate limits:
- `EAP_EXECUTOR_MAX_CONCURRENCY` (integer > 0, default `8`)
- `EAP_EXECUTOR_GLOBAL_RPS` (optional float > 0)
- `EAP_EXECUTOR_GLOBAL_BURST` (optional integer > 0, requires `EAP_EXECUTOR_GLOBAL_RPS`)
- `EAP_EXECUTOR_PER_TOOL_LIMITS_JSON` (optional JSON object)
  - Example:
    - `{"scrape_url":{"max_concurrency":2,"requests_per_second":5.0,"burst_capacity":2}}`

Pointer janitor (dashboard):
- `EAP_POINTER_JANITOR_ENABLED` (default: enabled)
- `EAP_POINTER_JANITOR_INTERVAL_SECONDS` (default: `300`)
- `EAP_POINTER_JANITOR_MAX_DELETE` (default: `200`)

OpenClaw routing header example:
- Global: `EAP_EXTRA_HEADERS_JSON='{"x-openclaw-agent-id":"my-agent"}'`
- Architect-only override: `EAP_ARCHITECT_EXTRA_HEADERS_JSON='{"x-openclaw-agent-id":"architect-agent"}'`

OpenAI Responses API mode example:
- Global responses path: `EAP_OPENAI_API_MODE=responses`
- Architect responses + auditor chat-completions split:
  - `EAP_ARCHITECT_OPENAI_API_MODE=responses`
  - `EAP_AUDITOR_OPENAI_API_MODE=chat_completions`

Mode guidance:
- Use `chat_completions` when you need streaming token output (`stream=true` path).
- Use `responses` when your gateway exposes `POST /v1/responses` and you want explicit Responses API compatibility.
- If `responses` endpoint is disabled/unsupported, EAP surfaces an explicit runtime error and you should switch mode back to `chat_completions`.

## Validation Rules

- Base URLs must start with `http://` or `https://`.
- Models and API keys cannot be empty strings.
- Timeout values must be integers greater than zero.
- Temperature must be a float greater than or equal to zero.
- OpenAI API mode must be `chat_completions` or `responses`.
- Extra header JSON values must be objects with non-empty string keys and values.
- Executor global concurrency must be a positive integer.
- Global burst capacity requires global RPS to be set.
- Per-tool limits JSON must be an object keyed by non-empty tool names.

# OpenClaw Interop Spike (EAP-071)

Status: Updated through EAP-075 (2026-02-23)  
Owner: EAP maintainers  
Scope: interoperability analysis plus implemented interop foundation (EAP-072, EAP-073, EAP-074, EAP-075)

## 1) Version Snapshot

This spike captures compatibility against these versions at analysis time:

- **EAP**: `0.1.7` (`/Users/ct/Desktop/efficient-agent-protocol/pyproject.toml`)
- **OpenClaw release**: `v2026.2.22` (published 2026-02-23)
- **OpenClaw docs/repo baseline**: `main` branch on 2026-02-23 (`package.json` currently `2026.2.23`)

Implication:
- Treat this as a moving-target snapshot for OpenClaw `main`.
- Interop CI pins and validates against:
  - `v2026.2.21`
  - `v2026.2.22`

## 2) Interop Surfaces (What We Checked)

OpenClaw-side surfaces:
- Gateway OpenAI-compatible HTTP endpoint: `POST /v1/chat/completions` (disabled by default).
- Gateway tools invoke HTTP endpoint: `POST /tools/invoke` (always enabled, policy-gated).
- Plugin system (TypeScript modules + required `openclaw.plugin.json` manifest).
- Skills system (`SKILL.md` directories, AgentSkills-compatible, with plugin-shipped skills support).

EAP-side surfaces:
- OpenAI-compatible provider adapter using `base_url + /v1/chat/completions`.
- Bearer auth header support.
- Python plugin system via `importlib.metadata` entry points (`eap.tool_plugins`).
- EAP runtime HTTP endpoints for `/v1/eap/*` execution/status/pointer summary.

## 3) Compatibility Matrix

| Capability | OpenClaw contract | EAP current state | Compatibility | Notes / EAP action |
| --- | --- | --- | --- | --- |
| LLM chat transport | `POST /v1/chat/completions` (OpenAI shape) | `OpenAIProvider` posts to `/v1/chat/completions` | **Compatible now** | Configure `EAP_BASE_URL` to OpenClaw gateway URL; endpoint must be enabled in OpenClaw config. |
| Gateway auth model | Bearer token, gateway auth mode token/password | EAP OpenAI provider sends `Authorization: Bearer <api_key>` | **Compatible now** | Set `EAP_API_KEY` to gateway token/password value used by OpenClaw auth mode. |
| OpenClaw agent selection | Preferred: `model: "openclaw:<agentId>"`; optional header `x-openclaw-agent-id` | EAP controls `model`, but does not set custom gateway headers | **Partial** | Use `EAP_MODEL=openclaw:<agentId>`; header-based routing would require EAP provider header extension. |
| Streaming chat | SSE for OpenAI endpoint when `stream=true` | EAP provider has SSE stream parsing for `data:` + `[DONE]` | **Compatible now** | Verify with real gateway in EAP-075 CI smoke. |
| OpenResponses API | `POST /v1/responses` (disabled by default) | No EAP provider for Responses API | **Gap** | Optional future adapter (not required for MVP interop). |
| Tool invocation API | `POST /tools/invoke`, policy + denylist enforced | No EAP client for this endpoint | **Gap** | Add dedicated client only if we need direct OpenClaw tool calls outside agent-turn flow. |
| Plugin runtime model | TypeScript/JavaScript in-process plugin modules, required `openclaw.plugin.json` | Adapter package added at `integrations/openclaw/eap-runtime-plugin` | **Compatible now (MVP)** | Plugin exports required tools and maps directly to EAP runtime endpoints. |
| Skills model | AgentSkills-style `SKILL.md`; plugin can ship skills via manifest `skills` field | Skill pack added at `integrations/openclaw/eap-runtime-plugin/skills` | **Compatible now (MVP)** | Includes `run`, `inspect`, `retry failed step`, and `export trace` skill workflows with quickstart docs. |
| External EAP control plane | OpenClaw plugins/tools can call external HTTP services | EAP runtime service now serves execute/run/pointer summary endpoints | **Compatible now (MVP)** | Bearer auth and JSON error envelopes are implemented and covered by integration tests. |

## 4) Auth Model Mapping

OpenClaw gateway auth (for HTTP endpoints):
- Bearer token required.
- Auth source depends on gateway mode:
  - `gateway.auth.mode="token"` -> token value
  - `gateway.auth.mode="password"` -> password value
- Excess failed auth attempts can return `429` with `Retry-After`.

EAP mapping:
- `EAP_API_KEY` maps directly to the bearer credential.
- No EAP auth handshake changes are required for `/v1/chat/completions` interop.

## 5) Plugin vs Skill Tradeoff (OpenClaw Integration Strategy)

### Plugin path (recommended for primary integration)

Pros:
- Can register real tools, HTTP handlers, RPC methods, background services.
- Best path for deep integration and controlled policy behavior.
- Can ship skills alongside plugin via manifest `skills` directories.

Cons:
- Requires Node/TypeScript packaging and OpenClaw plugin manifest/schema discipline.
- Higher implementation and maintenance cost than skills-only.

### Skill path (recommended as fast follow)

Pros:
- Fastest user-facing onboarding path.
- Good for operational commands and guardrailed workflows.
- Fits existing OpenClaw skill distribution model.

Cons:
- Skills are instructional/orchestration layer; not a full replacement for plugin-level runtime hooks.
- Less suited for deep protocol bridging without backing plugin/tool endpoints.

Recommended sequence:
1. Build minimal EAP HTTP runtime endpoints (EAP-072).
2. Build OpenClaw plugin adapter against those endpoints (EAP-073).
3. Ship OpenClaw skills that call the plugin/tooling path for common operations (EAP-074).

## 6) Known Limits / Risks Identified

1. **Agent routing header not configurable in EAP provider**
   - OpenClaw supports `x-openclaw-agent-id`; EAP currently cannot set custom headers in `OpenAIProvider`.
2. **OpenClaw endpoint toggles**
   - `/v1/chat/completions` is disabled by default; operators must enable it.
3. **Plugin model mismatch**
   - OpenClaw plugin system is TypeScript + manifest; EAP plugin system is Python entry points.
   - This is expected and should be handled via adapter package, not by forcing one model into the other.

## 7) Exit Criteria Check (EAP-071)

- [x] Compatibility matrix produced.
- [x] Auth model mapping documented.
- [x] Plugin vs skill tradeoffs documented.
- [x] Known limits captured with concrete next actions.

## 8) Recommended Next Item

`EAP-075` has now been implemented in-repo with:
- OpenClaw plugin adapter package at `integrations/openclaw/eap-runtime-plugin`
- required plugin tools:
  - `run_eap_workflow`
  - `get_eap_run_status`
  - `get_eap_pointer_summary`
- plugin manifest (`openclaw.plugin.json`) and local verification guide (`README.md`)
- bundled OpenClaw skill pack:
  - `eap_run_workflow`
  - `eap_inspect_run`
  - `eap_retry_failed_step`
  - `eap_export_trace`
- 5-minute skill quickstart at `integrations/openclaw/eap-runtime-plugin/skills/README.md`
- dedicated interop workflow: `.github/workflows/openclaw-interop.yml`
- OpenClaw compatibility smoke script: `scripts/interop_openclaw_smoke.sh`
- pinned version matrix:
  - `v2026.2.21`
  - `v2026.2.22`

Proceed to **EAP-077**:
- Add crash-safe resume and replay from persisted checkpoints.

## References (Primary Sources)

- OpenClaw release: [github.com/openclaw/openclaw/releases/tag/v2026.2.22](https://github.com/openclaw/openclaw/releases/tag/v2026.2.22)
- OpenClaw plugin system: [docs/tools/plugin.md](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/tools/plugin.md)
- OpenClaw plugin manifest: [docs/plugins/manifest.md](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/plugins/manifest.md)
- OpenClaw plugin agent tools: [docs/plugins/agent-tools.md](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/plugins/agent-tools.md)
- OpenClaw skills: [docs/tools/skills.md](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/tools/skills.md)
- OpenClaw OpenAI HTTP API: [docs/gateway/openai-http-api.md](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/gateway/openai-http-api.md)
- OpenClaw tools invoke API: [docs/gateway/tools-invoke-http-api.md](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/gateway/tools-invoke-http-api.md)
- OpenClaw security baseline: [docs/gateway/security/index.md](https://raw.githubusercontent.com/openclaw/openclaw/main/docs/gateway/security/index.md)

# SDK Contract (TypeScript + Go)

This document freezes the cross-language SDK contract for EAP macro planning/execution.

## Scope

The SDK contract standardizes payloads for:
- Chat completion (`chat`)
- Macro generation (`generate_macro`)
- Macro execution (`execute_macro`)
- Run resume (`resume_run`) via `POST /v1/eap/runs/{run_id}/resume`

The contract is transport-agnostic but is intended for JSON-over-HTTP.

## Authentication & Configuration

Required runtime settings:
- `base_url`: service endpoint root (for example `https://api.example.com`).
- `api_key`: bearer token for authenticated endpoints.
- `model`: default model name used by planning/chat operations.
- `timeout_seconds`: per-request timeout.

Auth rule:
- Send `Authorization: Bearer <api_key>` on every request unless explicitly running unauthenticated local mode.

Default headers:
- `Content-Type: application/json`
- `Accept: application/json`

## Common Envelope

All successful responses must include:
- `request_id` (string)
- `timestamp_utc` (ISO-8601 string)

All error responses must include:
- `error_type` (string)
- `message` (string)
- `details` (object, optional)

## Operation: `chat`

Request:
```json
{
  "model": "nemotron-orchestrator-8b",
  "messages": [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Summarize this file."}
  ],
  "temperature": 0.2
}
```

Response:
```json
{
  "request_id": "req_123",
  "timestamp_utc": "2026-02-23T12:00:00+00:00",
  "content": "Summary text..."
}
```

## Operation: `resume_run`

Resume an interrupted run from persisted checkpoint state.

Request:
```json
{
  "approvals": {
    "step_1": {"decision": "approve"}
  }
}
```

Endpoint:
- `POST /v1/eap/runs/{run_id}/resume`

Response:
```json
{
  "request_id": "req_999",
  "timestamp_utc": "2026-02-23T12:00:03+00:00",
  "run_id": "run_001",
  "pointer_id": "ptr_resume1234",
  "summary": "Completed step step_1 successfully.",
  "metadata": {
    "execution_run_id": "run_001",
    "resumed_from_checkpoint": true,
    "checkpoint_status": "completed"
  }
}
```

## Operation: `generate_macro`

Request:
```json
{
  "query": "Read README.md and summarize setup steps",
  "agent_manifest": {
    "read_local_file_abcd1234": {
      "type": "object",
      "properties": {"file_path": {"type": "string"}},
      "required": ["file_path"]
    }
  },
  "memory_context": "[user] prior context..."
}
```

Response:
```json
{
  "request_id": "req_456",
  "timestamp_utc": "2026-02-23T12:00:01+00:00",
  "macro": {
    "steps": [
      {
        "step_id": "step_1",
        "tool_name": "read_local_file_abcd1234",
        "arguments": {"file_path": "README.md"}
      }
    ],
    "return_final_state_only": true
  }
}
```

`macro` must validate against `BatchedMacroRequest` semantics:
- `steps[]` with unique `step_id`.
- Optional `retry_policy`.
- Optional `execution_limits`.
- Optional per-step HITL checkpoint (`ToolCall.approval`) and decisions map (`approvals`):
  - `approval.required=true` marks a step as approval-gated.
  - `approvals[step_id].decision` supports `approve | reject`.
  - `reject` decisions require `reason`.

## Operation: `execute_macro`

Request:
```json
{
  "macro": {
    "steps": [
      {
        "step_id": "step_1",
        "tool_name": "read_local_file_abcd1234",
        "arguments": {"file_path": "README.md"}
      }
    ],
    "return_final_state_only": true
  }
}
```

Response:
```json
{
  "request_id": "req_789",
  "timestamp_utc": "2026-02-23T12:00:02+00:00",
  "pointer_id": "ptr_abc12345",
  "summary": "Readme parsed successfully.",
  "metadata": {
    "execution_run_id": "run_001",
    "step_results": {}
  }
}
```

## Branching + Workflow Graph Compatibility

Visual builders must compile to `BatchedMacroRequest`-compatible output:
- `WorkflowGraphCompiler` validates persisted graph payloads.
- Compiled macro payloads must preserve `ToolCall.branching` target IDs.

## SDK Guarantees

- Stable JSON field names and value types across TypeScript and Go SDKs.
- ISO-8601 UTC timestamps for all time fields.
- Deterministic error envelope with machine-readable `error_type`.
- Backward-compatible additions only (new optional fields allowed; breaking removals/renames disallowed).

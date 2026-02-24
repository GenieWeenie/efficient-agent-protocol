# Built-in Tools

This document describes the built-in tools shipped in `environment.tools`.

## File tools

### `read_local_file`
- Purpose: Read UTF-8 text from a local file.
- Parameters:
  - `file_path` (`string`, required, `minLength=1`)
  - `max_characters` (`integer`, optional, `1..1000000`)
- Notes:
  - Rejects directories.
  - Fails when content exceeds `max_characters`.
  - Schema uses `additionalProperties: false`.

### `write_local_file`
- Purpose: Write or append UTF-8 text to a local file.
- Parameters:
  - `file_path` (`string`, required, `minLength=1`)
  - `content` (`string`, required)
  - `mode` (`string`, optional, enum: `overwrite|append`)
  - `create_directories` (`boolean`, optional)
- Notes:
  - Can create parent directories when `create_directories=true`.
  - Rejects directory paths.
  - Schema uses `additionalProperties: false`.

### `list_local_directory`
- Purpose: List directory entries and return JSON metadata.
- Parameters:
  - `directory_path` (`string`, required, `minLength=1`)
  - `recursive` (`boolean`, optional)
  - `include_hidden` (`boolean`, optional)
  - `max_entries` (`integer`, optional, `1..1000`)
- Notes:
  - Output includes `entries`, `entry_count`, and `truncated`.
  - Schema uses `additionalProperties: false`.

## Web/Data tools

### `scrape_url`
- Purpose: Fetch a webpage and return cleaned visible text.
- Parameters:
  - `url` (`string`, required, `minLength=1`)
  - `timeout_seconds` (`integer`, optional, `1..120`)
  - `max_bytes` (`integer`, optional, `1..10000000`)
  - `max_characters` (`integer`, optional, `1..500000`)
- Notes:
  - URL must be `http` or `https`.
  - Scripts/styles are removed before text extraction.
  - Schema uses `additionalProperties: false`.

### `fetch_json_url`
- Purpose: Fetch and parse JSON from a URL; return pretty-printed JSON.
- Parameters:
  - `url` (`string`, required, `minLength=1`)
  - `timeout_seconds` (`integer`, optional, `1..120`)
  - `max_bytes` (`integer`, optional, `1..10000000`)
- Notes:
  - Returns a runtime error when response is not valid JSON.
  - Schema uses `additionalProperties: false`.

### `extract_links_from_url`
- Purpose: Extract normalized links from a webpage; return JSON metadata.
- Parameters:
  - `url` (`string`, required, `minLength=1`)
  - `same_domain_only` (`boolean`, optional)
  - `include_text` (`boolean`, optional)
  - `timeout_seconds` (`integer`, optional, `1..120`)
  - `max_bytes` (`integer`, optional, `1..10000000`)
  - `max_links` (`integer`, optional, `1..5000`)
- Notes:
  - Output includes `links`, `link_count`, and `truncated`.
  - Schema uses `additionalProperties: false`.

## Interop tools

### `invoke_mcp_tool`
- Purpose: Call a tool exposed by an external MCP stdio server and return the MCP `tools/call` JSON result.
- Parameters:
  - `server_command` (`string`, required, `minLength=1`)
  - `tool_name` (`string`, required, `minLength=1`)
  - `tool_arguments` (`object`, optional)
  - `timeout_seconds` (`integer`, optional, `1..120`)
  - `working_directory` (`string`, optional, `minLength=1`)
  - `require_listed_tool` (`boolean`, optional)
- Notes:
  - Initializes MCP handshake (`initialize` + `notifications/initialized`) before invocation.
  - Can enforce that the target tool appears in `tools/list` before `tools/call`.
  - Returns JSON text payload from MCP result so downstream steps can parse it.
  - Schema uses `additionalProperties: false`.

### `invoke_openclaw_tool`
- Purpose: Call OpenClaw gateway `POST /tools/invoke` and return the JSON response payload.
- Parameters:
  - `base_url` (`string`, required, `minLength=1`)
  - `api_key` (`string`, required, `minLength=1`)
  - `tool_name` (`string`, required, `minLength=1`)
  - `tool_arguments` (`object`, optional)
  - `timeout_seconds` (`integer`, optional, `1..120`)
  - `account_id` (`string`, optional, `minLength=1`)
  - `channel_id` (`string`, optional, `minLength=1`)
- Notes:
  - Sends bearer auth via `Authorization: Bearer <api_key>`.
  - Supports OpenClaw multi-tenant routing headers:
    - `x-openclaw-account-id`
    - `x-openclaw-channel-id`
  - Maps gateway policy denials (`TOOL_INVOKE_POLICY_DENIED`) to normalized tool errors.
  - Returns JSON text payload so downstream steps can parse tool output.
  - Schema uses `additionalProperties: false`.

## Validation contract

Tool inputs are validated by `ToolRegistry.validate_arguments` before execution.
Supported constraints include:
- required fields
- primitive `type` checks
- `additionalProperties` enforcement
- `enum`
- `minLength` / `maxLength`
- `minimum` / `maximum`
- `minItems` / `maxItems`

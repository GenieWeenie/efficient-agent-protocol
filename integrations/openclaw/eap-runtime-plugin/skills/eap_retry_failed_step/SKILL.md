---
name: eap_retry_failed_step
description: Retry failed macro steps by re-running a reduced macro built from failed step trace data.
---

# EAP Retry Failed Step

Use this skill when an EAP run has one or more failed steps.

## Required Tools

- `get_eap_run_status`
- `run_eap_workflow`

## Inputs

- `run_id` (string)
- `requestTimeoutMs` (optional integer)

## Procedure

1. Call `get_eap_run_status` for `run_id`.
2. Validate `summary.failed_steps > 0`. If not, stop and report "no failed steps to retry."
3. Inspect `trace_events` and collect failed step call details:
   - `step_id`
   - `tool_name`
   - `arguments`
4. Build a retry macro:
   - `steps`: failed steps only
   - preserve each failed step `step_id`, `tool_name`, and `arguments`
5. Call `run_eap_workflow` with this retry macro.
6. Return retry identifiers and a comparison of old vs new failed counts.

## Safety Rules

- Do not invent missing arguments.
- If failed step arguments are unavailable in trace, stop and return a manual-retry warning.
- Keep retry macro scoped only to failed steps.

## Output Contract

Return:

- `original_run_id`
- `retry_run_id`
- `retry_pointer_id`
- `retry_summary`
- `notes` (including any manual-retry requirement)

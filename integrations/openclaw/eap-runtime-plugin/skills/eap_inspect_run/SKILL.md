---
name: eap_inspect_run
description: Inspect execution state for an EAP run and summarize pass/fail outcomes with trace counts.
---

# EAP Inspect Run

Use this skill to check run health, completion status, and trace detail after execution starts.

## Required Tool

- `get_eap_run_status`

## Inputs

- `run_id` (string)
- `requestTimeoutMs` (optional integer)

## Procedure

1. Call `get_eap_run_status` for `run_id`.
2. Extract:
   - `status`
   - `summary.total_steps`
   - `summary.succeeded_steps`
   - `summary.failed_steps`
   - `trace_event_count`
3. If `failed_steps > 0`, recommend `eap_retry_failed_step`.
4. If no failures, report run as healthy.

## Output Contract

Return:

- `run_id`
- `status`
- `totals`: `{ total_steps, succeeded_steps, failed_steps }`
- `trace_event_count`
- `next_recommended_skill` (`eap_retry_failed_step` or `none`)

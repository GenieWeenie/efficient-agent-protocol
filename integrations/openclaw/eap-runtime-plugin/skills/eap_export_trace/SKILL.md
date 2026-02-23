---
name: eap_export_trace
description: Export a concise diagnostic trace report for a run, optionally enriched with pointer summary metadata.
---

# EAP Export Trace

Use this skill when you need a shareable failure/success report for debugging or incident review.

## Required Tools

- `get_eap_run_status`
- `get_eap_pointer_summary` (optional if `pointer_id` is provided)

## Inputs

- `run_id` (string)
- `pointer_id` (optional string)
- `requestTimeoutMs` (optional integer)

## Procedure

1. Call `get_eap_run_status` using `run_id`.
2. Build a report with:
   - run status and totals
   - trace event count
   - a compact event timeline (`event_type`, `step_id`, `timestamp_utc` if present)
3. If `pointer_id` is provided, call `get_eap_pointer_summary` and append pointer lifecycle metadata.
4. Return report as Markdown fenced block for easy copy/paste into issues.

## Output Contract

Return:

- `run_id`
- `status`
- `trace_event_count`
- `report_markdown`

---
name: eap_run_workflow
description: Execute an EAP macro and capture run and pointer identifiers for follow-up operations.
---

# EAP Run Workflow

Use this skill when you already have a valid EAP `macro` payload and need to start execution.

## Required Tool

- `run_eap_workflow`

## Inputs

- `macro` (object): valid EAP `BatchedMacroRequest`
- `requestTimeoutMs` (optional integer)

## Procedure

1. Call `run_eap_workflow` with the supplied `macro`.
2. Parse and return:
   - `pointer_id`
   - `metadata.execution_run_id` as `run_id`
   - `summary`
3. If the response is an error, include the upstream `error_type`/`message` and stop.

## Output Contract

Return a short structured summary:

- `run_id`
- `pointer_id`
- `summary`
- `next_recommended_skill`: `eap_inspect_run`

# OpenClaw Skill Pack (EAP-074)

This skill pack is shipped with the EAP OpenClaw plugin and covers common runtime operations:

- `eap_run_workflow`
- `eap_inspect_run`
- `eap_retry_failed_step`
- `eap_export_trace`

## 5-Minute Quickstart

1. Ensure plugin config points to a live EAP runtime (`baseUrl`, optional `apiKey`).
2. Allow plugin tools:
   - `run_eap_workflow`
   - `get_eap_run_status`
   - `get_eap_pointer_summary`
3. Enable all four skills from `integrations/openclaw/eap-runtime-plugin/skills/`.
4. Execute a macro using the `eap_run_workflow` skill.
5. Inspect with `eap_inspect_run`.
6. If failed steps exist, use `eap_retry_failed_step`.
7. Generate a shareable report with `eap_export_trace`.

## Files

- `skills/eap_run_workflow/SKILL.md`
- `skills/eap_inspect_run/SKILL.md`
- `skills/eap_retry_failed_step/SKILL.md`
- `skills/eap_export_trace/SKILL.md`

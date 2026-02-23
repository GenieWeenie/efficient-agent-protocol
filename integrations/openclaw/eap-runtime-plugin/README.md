# OpenClaw EAP Runtime Plugin (EAP-073)

This plugin exposes EAP runtime HTTP operations as OpenClaw tools:

- `run_eap_workflow`
- `get_eap_run_status`
- `get_eap_pointer_summary`

It also ships an OpenClaw skill pack for common operations:

- `eap_run_workflow`
- `eap_inspect_run`
- `eap_retry_failed_step`
- `eap_export_trace`

## Requirements

- OpenClaw with plugin support enabled
- EAP runtime HTTP server reachable (EAP-072 endpoints)
- Node.js 18+

## Tool Mapping

- `run_eap_workflow` -> `POST /v1/eap/macro/execute`
- `get_eap_run_status` -> `GET /v1/eap/runs/{run_id}`
- `get_eap_pointer_summary` -> `GET /v1/eap/pointers/{pointer_id}/summary`

## Plugin Config

`openclaw.plugin.json` defines:

- `baseUrl` (required): EAP runtime base URL
- `apiKey` (optional): bearer token if EAP runtime requires auth
- `timeoutMs` (optional): request timeout in milliseconds (default `15000`)

You can also override with environment variables:

- `EAP_RUNTIME_BASE_URL`
- `EAP_RUNTIME_API_KEY`
- `EAP_RUNTIME_TIMEOUT_MS`

## Local Verification

1. Start EAP runtime server in your local setup.
2. Install plugin dependencies:

```bash
cd integrations/openclaw/eap-runtime-plugin
npm install
```

3. Run plugin unit tests:

```bash
npm test
```

4. Register plugin in OpenClaw and allow these tools:
   - `run_eap_workflow`
   - `get_eap_run_status`
   - `get_eap_pointer_summary`
5. Enable the bundled skills from `./skills/`.
6. Invoke `run_eap_workflow` with a valid EAP macro payload.
7. Use returned `metadata.execution_run_id` with `get_eap_run_status`.
8. Use returned `pointer_id` with `get_eap_pointer_summary`.

Successful completion of steps 6-8 is the EAP-073 acceptance check.
For EAP-074 skill-pack acceptance, run the flow in `skills/README.md`.

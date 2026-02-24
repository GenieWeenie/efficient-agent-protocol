# EAP Proof Sheet: Why EAP Now

Updated: 2026-02-24  
Scope: EAP `0.1.7` with OpenClaw interop, eval gating, and operator telemetry (EAP-071 to EAP-082 complete).

## Side-by-Side Capability Table

| Capability | EAP runtime status | OpenClaw interop status | Evidence |
| --- | --- | --- | --- |
| OpenAI-compatible execution API | Native (`POST /v1/eap/execute` and related run/pointer endpoints) | Plugin tools call EAP runtime over HTTP | `app.py`, `tests/integration/test_runtime_http_api.py`, `integrations/openclaw/eap-runtime-plugin` |
| Plugin and skills integration | EAP side exposes stable runtime contract | OpenClaw plugin + skill pack MVP shipped | `integrations/openclaw/eap-runtime-plugin/openclaw.plugin.json`, `integrations/openclaw/eap-runtime-plugin/skills/README.md`, `tests/contract/test_openclaw_skill_pack.py` |
| Human-in-the-loop approvals | Step-level `approval_required/approved/rejected` transitions persisted in traces | Available through runtime endpoints and resume flow | `tests/integration/test_human_approval.py`, `tests/integration/test_runtime_http_api.py` |
| Crash-safe resume/replay | Checkpointed runs can resume deterministically after interruption | Runtime resume endpoint available to plugin clients | `tests/integration/test_resume_replay.py`, `tests/integration/test_runtime_http_api.py` |
| MCP tool interoperability | Built-in `invoke_mcp_tool` bridge in runtime tool registry | Can be invoked in EAP workflows used by interop flows | `environment/tools/mcp_tools.py`, `tests/integration/test_mcp_interop.py` |
| CI-gated quality scorecard | Correctness/reliability/latency harness with hard thresholds | Runs as required CI lane on PR/push | `scripts/eval_scorecard.py`, `.github/workflows/ci.yml`, `docs/eval_thresholds.json` |
| Operator diagnostics | Dashboard-ready retry/failure/latency/saturation telemetry export | Maintainers can triage failed runs from artifacts only | `scripts/export_telemetry_pack.py`, `docs/operator_telemetry_pack.md`, `tests/integration/test_telemetry_pack.py` |

## Reproducible Commands

### 1) Interop evidence (plugin + skills + runtime contract)

```bash
npm --prefix integrations/openclaw/eap-runtime-plugin ci
npm --prefix integrations/openclaw/eap-runtime-plugin test
./scripts/interop_openclaw_smoke.sh v2026.2.22
python -m pytest -q \
  tests/contract/test_openclaw_skill_pack.py \
  tests/integration/test_runtime_http_api.py \
  tests/integration/test_mcp_interop.py
```

### 2) Eval scorecard evidence (regression-gated)

```bash
python scripts/eval_scorecard.py \
  --output-dir artifacts/eval \
  --threshold-config docs/eval_thresholds.json \
  --baseline docs/eval_baseline.json
```

Expected output:
- `artifacts/eval/scorecard.json`
- `artifacts/eval/scorecard.md`
- `artifacts/eval/trend.json`
- `artifacts/eval/history.ndjson`

### 3) Telemetry evidence (failed-run diagnosis)

```bash
python -m pytest -q tests/integration/test_telemetry_pack.py
python scripts/export_telemetry_pack.py \
  --db-path agent_state.db \
  --output-dir artifacts/telemetry
```

Expected output:
- `artifacts/telemetry/failed_run_diagnostics.json`
- `artifacts/telemetry/operator_report.md`

## Evidence Snapshot

Source: `docs/benchmarks.md` and `docs/eval_thresholds.json`

- Perf baseline (2026-02-23): concurrency path `0.28s`, rate-limit saturation path `1.70s`.
- Eval gate thresholds:
  - correctness pass rate `>= 1.0`
  - reliability pass rate `>= 1.0`
  - latency `p95 <= 300ms`, `max <= 500ms`
- CI enforces these gates on every PR via `Eval scorecard (py3.11)`.

## Decision Rule

Choose EAP now if you need strong failure semantics, resumable execution, OpenClaw/MCP interop, and operator-grade diagnostics with reproducible CI evidence.

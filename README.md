# Efficient Agent Protocol (EAP)

[![CI](https://github.com/GenieWeenie/efficient-agent-protocol/actions/workflows/ci.yml/badge.svg)](https://github.com/GenieWeenie/efficient-agent-protocol/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

> Status: Experimental (pre-1.0). APIs and schema may change.
> See `STABILITY.md` and `ROADMAP.md` for guarantees and planned milestones.
> Latest stable release: `v0.1.7`

Efficient Agent Protocol is a local-first framework for multi-step tool workflows.
It stores large outputs as pointer-backed state (`ptr_*`) and runs dependency-aware DAG steps in parallel.
It also ships OpenClaw interop paths for gateway/tool integration.

## 30-Second Pitch

- EAP is the reliability layer for agent workflows: deterministic execution, resumable runs, and pointer-backed state.
- It is built for local-first teams that need control over failure behavior, replayability, and traceability.
- It integrates with existing ecosystems instead of forcing a rewrite (`chat_completions`, `responses`, OpenClaw tooling, MCP tools).

See `docs/eap_proof_sheet.md` for reproducible evidence and command-level validation.

## Why Choose EAP

| If you need | EAP gives you |
| --- | --- |
| Large outputs without prompt bloat | Pointer-backed state (`ptr_*`) passed between steps |
| Predictable behavior under failure | DAG scheduling, retries, typed errors, and checkpointed resume/replay |
| Human control at critical steps | Step-level HITL checkpoints (`approval_required`, `approved`, `rejected`) |
| Operator-grade confidence | Trace visibility, telemetry export pack, and CI eval threshold gates |
| Portability across runtimes | OpenAI-compatible providers + OpenClaw bridge + MCP bridge |

## Where EAP Fits

Best for:
- Python developers building local-first orchestration with explicit execution semantics.
- Teams that care about observability, replayability, and controlled failure behavior.

Not ideal yet:
- strict long-term API compatibility requirements before `v1.0`
- non-technical users expecting zero-configuration onboarding
- teams that want a fully managed hosted control plane instead of running local/runtime components

## Current Limits (Honest)

- Pre-1.0 contract: APIs and schema can still change (`STABILITY.md`).
- `responses` streaming behavior depends on gateway SSE event support and can vary by gateway release/configuration.
- This is an engineering-first runtime, not a no-code platform.

## What You Get

- Pointer-based state to keep prompts small
- Parallel DAG execution with retries and validation
- Human-in-the-loop checkpoints (`approval_required`, `approved`, `rejected`)
- Crash-safe resume/replay from persisted run checkpoints
- Evaluation harness with CI threshold gates (`scripts/eval_scorecard.py`)
- Operator telemetry pack export (`scripts/export_telemetry_pack.py`)
- Built-in chat UI (Streamlit) with trace + data inspection
- Conversation memory (full/window/summary)
- Pluggable pointer storage backends (SQLite, Redis, PostgreSQL)
- OpenClaw and MCP interop:
  - OpenAI-compatible modes: `chat_completions` and `responses`
  - Gateway tool bridge for `POST /tools/invoke`
  - OpenClaw plugin + skills starter package in `integrations/openclaw/eap-runtime-plugin`
  - MCP tool bridge (`invoke_mcp_tool`)

## Why Not Just Use A Generic Agent Framework?

- If you mainly need prompting convenience and managed UX, a platform suite may be simpler.
- If you need explicit run-state contracts, replayability, and pointer-backed payload discipline, EAP is a stronger fit.
- If you need to integrate with OpenClaw without rewriting your runtime, EAP now has first-party bridge paths.

## Quickstart (GitHub-first)

Requirements:
- Python 3.9+

1. Install

```bash
git clone https://github.com/GenieWeenie/efficient-agent-protocol.git
cd efficient-agent-protocol
pip install -e .
```

2. Configure

```bash
cp .env.example .env
```

Minimum variables:

```bash
EAP_BASE_URL=http://localhost:1234
EAP_MODEL=nemotron-orchestrator-8b
EAP_API_KEY=not-needed
```

3. Smoke test

```bash
python -m examples.01_minimal
```

4. Run dashboard

```bash
pip install streamlit pandas
streamlit run app.py
```

5. Use it

- Open `http://localhost:8501`
- In **Agent Chat**, ask for a task
- Check **Data Inspector** for pointer payloads
- Check **Execution Trace** for step timing/retries/errors

6. Try starter packs

```bash
python -m starter_packs.research_assistant --question "What are launch risks?"
python -m starter_packs.doc_ops --focus "summarize priorities and actions"
python -m starter_packs.local_etl
```

7. Optional OpenClaw smoke check

```bash
./scripts/interop_openclaw_smoke.sh v2026.2.22
```

## Programmatic Example

```python
from eap.protocol import StateManager
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import read_local_file, READ_FILE_SCHEMA
from eap.agent import AgentClient

state_manager = StateManager()
registry = ToolRegistry()
registry.register("read_local_file", read_local_file, READ_FILE_SCHEMA)
executor = AsyncLocalExecutor(state_manager, registry)

architect = AgentClient(
    base_url="http://localhost:1234",
    model_name="nemotron-orchestrator-8b",
    provider_name="local",
)

manifest = registry.get_agent_manifest()
macro = architect.generate_macro("Read README.md and summarize setup steps", manifest)
# asyncio.run(executor.execute_macro(macro))
```

## Common Commands

```bash
python3 -m pytest -q
pre-commit run --all-files
python3 scripts/migrate_state_db.py --db-path agent_state.db --dry-run
python3 scripts/export_metrics.py --db-path agent_state.db --output metrics/latest.json
python3 scripts/export_telemetry_pack.py --db-path agent_state.db --output-dir artifacts/telemetry
./scripts/interop_openclaw_smoke.sh v2026.2.22
python3 -m build
```

## Docs

- Start here:
  - `docs/eap_proof_sheet.md`
  - `docs/configuration.md`
  - `docs/architecture.md`
  - `docs/troubleshooting.md`
- Contract and policy:
  - `STABILITY.md`
  - `ROADMAP.md`
  - `docs/v1_contract.md`
  - `SECURITY.md`
  - `CONTRIBUTING.md`
- Runtime and operations:
  - `docs/workflow_schema.md`
  - `docs/tools.md`
  - `docs/observability.md`
  - `docs/operator_telemetry_pack.md`
  - `docs/migrations.md`
- Interop and starter packs:
  - `docs/openclaw_interop.md`
  - `integrations/openclaw/eap-runtime-plugin/README.md`
  - `docs/starter_packs/README.md`
- GitHub roadmap board: https://github.com/users/GenieWeenie/projects/1

# Efficient Agent Protocol (EAP)

[![CI](https://github.com/GenieWeenie/efficient-agent-protocol/actions/workflows/ci.yml/badge.svg)](https://github.com/GenieWeenie/efficient-agent-protocol/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

Efficient Agent Protocol is a local-first framework for multi-step tool workflows.
It stores large outputs as pointer-backed state (`ptr_*`) and runs dependency-aware DAG steps in parallel.

## What You Get

- Pointer-based state to keep prompts small
- Parallel DAG execution with retries and validation
- Built-in chat UI (Streamlit) with trace + data inspection
- Conversation memory (full/window/summary)
- Pluggable pointer storage backends (SQLite, Redis, PostgreSQL)

## Quickstart (GitHub-first)

Requirements:
- Python 3.9+

1. Install

```bash
git clone https://github.com/GenieWeenie/efficient-agent-protocol.git
cd efficient-agent-protocol
pip install -e .
pip install streamlit pandas
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

3. Run dashboard

```bash
streamlit run app.py
```

4. Use it

- Open `http://localhost:8501`
- In **Agent Chat**, ask for a task
- Check **Data Inspector** for pointer payloads
- Check **Execution Trace** for step timing/retries/errors

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
python3 -m build
```

## Docs

- `docs/configuration.md`
- `docs/architecture.md`
- `docs/tools.md`
- `docs/workflow_schema.md`
- `docs/storage_lifecycle.md`
- `docs/storage_backends.md`
- `docs/sdk_contract.md`
- `docs/distributed_execution.md`
- `docs/troubleshooting.md`

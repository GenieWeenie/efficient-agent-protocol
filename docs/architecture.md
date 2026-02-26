# Architecture

This document describes the end-to-end runtime architecture of Efficient Agent Protocol (EAP).

Related deep dives:

- `docs/custom_tool_authoring.md`
- `docs/pointer_internals.md`

## System Boundary

EAP has four runtime planes:

1. Planning plane: LLM-assisted macro generation (`AgentClient`, compiler).
2. Execution plane: deterministic DAG scheduling (`AsyncLocalExecutor`).
3. State plane: pointer-backed persistence and run observability (`StateManager` + pointer store backend).
4. Operations plane: local UI and HTTP control surface (Streamlit + `EAPRuntimeHTTPServer`).

## End-To-End Flow

1. User/task input is converted into a macro plan (`BatchedMacroRequest`) with ordered `ToolCall` steps.
2. `MacroCompiler` validates and normalizes macro payload contracts.
3. `AsyncLocalExecutor.execute_macro(...)` initializes run state, actor metadata, and checkpoint record.
4. Executor schedules all steps concurrently, but each step waits for dependency futures and branch gates.
5. Step arguments are resolved:
   - literal arguments pass through as-is
   - `"$step:<id>"`/`"$<id>"` resolves to upstream pointer payload
   - `"ptr_*"` directly resolves persisted pointer payload
6. `ToolRegistry.validate_arguments(...)` validates resolved arguments against tool schema.
7. Executor invokes the tool callable with retry, backoff, concurrency, and rate-limit controls.
8. Tool output (or structured error/skip/reject payload) is stored via `StateManager.store_and_point(...)`.
9. Executor appends trace events and updates checkpoint state after each step transition.
10. Run completion writes summary + diagnostics and returns a final pointer response.
11. If run paused (`approval_required`) or process interrupted, `resume_run(...)` rehydrates checkpoint and replays completed steps from stored pointers.

## Runtime Component Map

### Contracts And Models (`protocol/models.py`)

- Macro/run contracts: `ToolCall`, `BatchedMacroRequest`, `RetryPolicy`, `ExecutionLimits`.
- Branching + HITL contracts: `BranchingRule`, `StepApprovalCheckpoint`, `StepApprovalDecision`.
- Trace contract: `ExecutionTraceEvent` + strict lifecycle event types.
- Conversation models: `ConversationSession`, `ConversationTurn`, `MemoryStrategy`.
- Workflow graph contracts: `PersistedWorkflowGraph`, `WorkflowGraphNode`, `WorkflowGraphEdge`.

### State Plane (`protocol/state_manager.py`)

- Pointer response lifecycle (`ptr_*`) and pointer backend orchestration.
- Persistent execution artifacts:
  - `execution_trace_events`
  - `execution_run_summaries`
  - `execution_run_checkpoints`
  - `execution_run_diagnostics`
- Conversation persistence and memory-policy enforcement (`full`, `window`, `summary`).
- Operational metrics export (`collect_operational_metrics`, `export_operational_metrics`).

### Pointer Storage Layer (`protocol/storage/*`)

- `PointerStoreBackend` is the pluggable backend contract.
- `SQLitePointerStore` is default local backend.
- `RedisPointerStore` supports in-memory/networked deployments.
- `PostgresPointerStore` supports external durable datastore deployments.

All backends support lifecycle fields (`created_at_utc`, `ttl_seconds`, `expires_at_utc`) and shared expiry cleanup semantics.

### Execution Plane (`environment/executor.py`)

- Dependency-aware parallel scheduling with per-step futures.
- Branch activation/deactivation routing (`true`, `false`, `fallback`, optional early exit).
- HITL transitions: `approval_required`, `approved`, `rejected`, `paused`.
- Retry policy with typed error handling.
- Global and per-tool guardrails:
  - max concurrency semaphores
  - token-bucket request-rate limits
- Crash-safe checkpoints and deterministic replay on resume.
- Saturation + approval metrics attached to final run metadata.

### Tool Plane (`environment/tool_registry.py`, `environment/plugin_loader.py`)

- Tool registration (`name`, callable, JSON schema).
- Deterministic hashed IDs for planner-facing manifest compaction.
- Runtime schema argument validation before invocation.
- Plugin loading through Python entry points (`eap.tool_plugins`) with strict/non-strict modes.

### Planning Plane (`agent/*`)

- `AgentClient`: provider-backed planner prompt assembly + memory context injection.
- `MacroCompiler`: sanitizes/validates planner JSON macro payloads.
- `WorkflowGraphCompiler`: compiles persisted visual DAG graphs to executable macro requests.
- Provider adapters (`agent/providers/*`): OpenAI-compatible, Anthropic, Gemini.

### Distributed Worker Path (`environment/distributed_executor.py`)

- Optional coordinator for queue/lease/heartbeat-based step claiming.
- Supports claimed-step execution with pointer persistence and finalization reporting.
- Used when multi-worker processing is required beyond single-process executor mode.

## Operations Plane

### Runtime HTTP API (`eap/runtime/http_api.py`)

Primary endpoints:

- `POST /v1/eap/macro/execute`
- `POST /v1/eap/runs/{run_id}/resume`
- `GET /v1/eap/runs/{run_id}`
- `GET /v1/eap/pointers/{pointer_id}/summary`

Runtime API includes:

- scoped bearer-token auth and actor ownership checks
- operation-level rate limiting and concurrency throttles
- trace/summary retrieval for external orchestrators (OpenClaw/MCP integrations)

### Local UI (`app.py`)

- Chat orchestration path for macro generation/execution.
- Data inspector for pointer payloads.
- Trace views for step lifecycle and diagnostics.

## Core Data Flows

### Pointer Flow

1. Step output -> `store_and_point(...)` -> pointer ID.
2. Pointer ID propagates through step dependencies and run metadata.
3. Downstream step dereferences pointer on argument resolution.
4. UI/API inspects pointer summary + metadata without loading entire raw artifact into planner context.

Detailed pointer internals: `docs/pointer_internals.md`.

### Trace And Replay Flow

1. Executor emits lifecycle events (`queued`, `started`, `completed`, `failed`, etc.).
2. Checkpoint persists run status + step pointer map + branch decisions.
3. Resume path reloads checkpoint and marks completed steps as `replayed`.
4. Final diagnostics snapshot records replayed steps and saturation metrics.

## Extension Points

### Add New Tools

- Register callable + schema via `ToolRegistry.register(...)`.
- Optionally package as plugin entry point for external distribution.
- Validate with unit + integration tests before enabling in runtime.

Guide: `docs/custom_tool_authoring.md`.

### Add/Swap Pointer Backend

- Implement `PointerStoreBackend`.
- Pass backend into `StateManager(pointer_store=...)`.
- Ensure lifecycle + expiry methods behave consistently with contract.

Guide: `docs/pointer_internals.md`.

### Add Planner Providers

- Implement provider adapter matching `LLMProvider` contract.
- Wire into provider factory and tests.
- Keep planner outputs within `BatchedMacroRequest` schema contract.

## Design Guarantees

- Local-first durability by default.
- Deterministic typed error surfaces for failure handling.
- Small planner context through pointer indirection.
- Explicit replay semantics from persisted checkpoints.
- Observability artifacts as first-class runtime outputs.

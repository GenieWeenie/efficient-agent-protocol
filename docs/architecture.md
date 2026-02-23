# Architecture

This document describes the runtime architecture of Efficient Agent Protocol (EAP).

## High-Level Flow

1. `AgentClient` creates a macro plan (`BatchedMacroRequest`) from user input.
2. `MacroCompiler` sanitizes and validates LLM JSON output.
3. `AsyncLocalExecutor` executes macro steps as a dependency-aware DAG.
4. `StateManager` persists step outputs through a pluggable pointer store and returns `ptr_*` pointers.
5. Executor emits and persists execution trace events and run summaries.
6. Streamlit dashboard (`app.py`) provides chat, data inspection, and trace views.

## Core Components

## `protocol/models.py`
- Core Pydantic contracts (`ToolCall`, `BatchedMacroRequest`, `RetryPolicy`, error payloads).
- Execution trace model (`ExecutionTraceEvent`) with lifecycle states:
  - `queued`, `approval_required`, `approved`, `rejected`, `started`, `retried`, `failed`, `completed`
- Conversation memory models:
  - `ConversationSession`, `ConversationTurn`, `MemoryStrategy`
- Workflow graph models:
  - `PersistedWorkflowGraph`, `WorkflowGraphNode`, `WorkflowGraphEdge`

## `protocol/state_manager.py`
- Pointer vault orchestration via `PointerStoreBackend`.
- Execution observability persistence:
  - `execution_trace_events`
  - `execution_run_summaries`
- Conversation persistence:
  - `conversation_sessions`
  - `conversation_turns`
- Memory policy application (`full`, `window`, `summary`).

## `protocol/storage/*`
- `PointerStoreBackend` defines common pointer store/retrieve/list/delete contract.
- `SQLitePointerStore` provides the default local backend with lifecycle metadata support.
- `RedisPointerStore` provides a Redis-backed pointer vault implementation.
- `PostgresPointerStore` provides a PostgreSQL-backed pointer vault implementation.

## `environment/executor.py`
- Executes step functions in parallel when dependencies allow.
- Resolves `$step:<id>` pointer references.
- Performs schema validation before tool invocation.
- Enforces global/per-tool semaphores and token-bucket rate limits.
- Applies retry policy with backoff on retryable failures.
- Writes trace events and run summary metadata.
- Emits saturation metrics in final result metadata.

## `environment/distributed_executor.py`
- Provides a SQLite-backed coordinator for distributed worker leases.
- Supports enqueue, claim, heartbeat, completion, and failure reporting.
- Includes a worker loop to execute claimed steps and persist pointer outputs.

## `environment/tool_registry.py`
- Registers tools and JSON schemas.
- Produces hashed manifest for architect planning.
- Exposes deterministic `get_agent_manifest()` (`hashed_tool_id -> parameters`).
- Validates runtime arguments against schema contracts.
- Validates and registers plugin manifests.

## `environment/plugin_loader.py`
- Discovers third-party plugins via Python entry points (`eap.tool_plugins`).
- Loads plugin manifests and registers their tools into `ToolRegistry`.
- Supports strict/non-strict loading modes for startup safety.

## `agent/agent_client.py`
- Prompt assembly for planning/auditing.
- Memory-context injection for multi-turn planning.
- Provider-backed chat/macro generation.

## `agent/compiler.py`
- `MacroCompiler` sanitizes and validates LLM macro JSON.
- `WorkflowGraphCompiler` validates persisted workflow graph payloads and compiles them to `BatchedMacroRequest`.

## `agent/providers/*`
- Provider abstraction interface (`LLMProvider`).
- Concrete adapters:
  - OpenAI-compatible
  - Anthropic
  - Google Gemini
- Provider selection/fallback factory.

## Runtime Data Model

## Pointer Vault
- Large tool payloads are persisted through a backend implementation (SQLite by default).
- LLM-facing state is reduced to lightweight pointers plus summaries.
- Pointer IDs are referenced across steps and turns.
- Pointer lifecycle tracks `created_at_utc`, optional `ttl_seconds`, and `expires_at_utc`.

## Execution Trace
- Every step lifecycle event is persisted with:
  - run ID
  - step ID
  - tool name
  - timing
  - retry/failure details
- Run-level summary stores total duration and success/failure counts.

## Conversation Memory
- Sessions group turns.
- Turns can reference pointer IDs and macro run IDs.
- Memory strategy controls retained context size.

## Design Principles

- Local-first persistence: state survives process restarts.
- Small LLM context: heavy data remains out of prompt context.
- Deterministic failure contracts: structured, typed errors.
- Observability by default: traces and summaries are first-class artifacts.
- Provider portability: swap model backends without changing agent logic.

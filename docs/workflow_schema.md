# Workflow Graph Schema

`PersistedWorkflowGraph` is the persisted format for visual workflow editing and round-trips to executable macros.

Source model: `protocol/models.py`

## Core Types

## `WorkflowGraphNode`
- `node_id`: stable graph node identifier.
- `step`: embedded `ToolCall` (includes `tool_name`, `arguments`, `step_id`, optional `branching`, optional `approval` checkpoint metadata).
- `label`, `position_x`, `position_y`: editor-only metadata.

## `WorkflowGraphEdge`
- `source_node_id`, `target_node_id`: directed edge endpoints.
- `kind`:
  - `dependency`: execution dependency ordering edge.
  - `branch_true`: visual branch edge for `BranchingRule.true_target_step_ids`.
  - `branch_false`: visual branch edge for `BranchingRule.false_target_step_ids`.
  - `branch_fallback`: visual branch edge for `BranchingRule.fallback_target_step_ids`.

## `PersistedWorkflowGraph`
- `workflow_id`: stable ID.
- `version`: schema version.
- `nodes`: list of `WorkflowGraphNode`.
- `edges`: list of `WorkflowGraphEdge`.
- `created_at_utc`, `updated_at_utc`, `metadata`.

## Validation Rules

- Graph must contain at least one node.
- `node_id` values must be unique.
- Embedded `step.step_id` values must be unique.
- Edges must reference valid source/target nodes.
- Dependency edges must be acyclic.
- Branch edges require source node branching metadata.
- Branch edges must exactly match branching target step IDs by branch kind:
  - `branch_true` == `true_target_step_ids`
  - `branch_false` == `false_target_step_ids`
  - `branch_fallback` == `fallback_target_step_ids`

## Compilation to Runtime Macro

Use `PersistedWorkflowGraph.to_batched_macro_request(...)`.
For compiler entry points from UI/storage payloads, use `WorkflowGraphCompiler.compile_to_macro(...)` in `agent/compiler.py`.

Compilation behavior:
1. Topologically sort nodes by `dependency` edges.
2. Emit embedded `ToolCall` steps in sorted order.
3. Preserve embedded branching metadata from each `ToolCall`.
4. Construct `BatchedMacroRequest` (optionally with supplied retry/execution limits).

This keeps the visual graph format and executable macro format aligned without lossy conversion.

## Branch Condition Security Posture

Branch conditions are executed through a constrained evaluator, not Python `eval`.

Allowed expression semantics:

- boolean operators: `and`, `or`, `not`
- comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `is`, `is not`
- literal constants: string, number, boolean, null/None
- literal containers: list, tuple, set, dict
- resolved step references after `$step:<id>[.<path>]` interpolation

Rejected constructs include (non-exhaustive):

- function or method calls
- attribute access
- indexing/subscript expressions
- arithmetic expressions and comprehensions
- any non-boolean final result

Operational guidance:

1. Keep conditions simple and deterministic.
2. Use pointer-resolved metadata/value checks instead of executable logic.
3. Treat validation failures as policy violations and fix workflow definitions rather than bypassing checks.

# protocol/models.py
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

class PointerResponse(BaseModel):
    """
    The lightweight payload sent back to the LLM instead of raw data.
    """
    pointer_id: str = Field(..., description="The unique ID referencing the stored data.")
    summary: str = Field(..., description="A high-level summary of the execution result.")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Optional context (e.g., item count, status codes, truncation warnings)."
    )


class ToolErrorPayload(BaseModel):
    """Normalized tool failure contract for executor/UI consumers."""

    error_type: str = Field(
        ...,
        description=(
            "validation_error | dependency_error | tool_execution_error | approval_rejected"
        ),
    )
    message: str = Field(..., description="Short human-readable failure reason.")
    step_id: str = Field(..., description="Step ID where the failure occurred.")
    tool_name: str = Field(..., description="Tool name/hash that failed.")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional structured error metadata.")


class StepApprovalCheckpoint(BaseModel):
    """Optional HITL approval checkpoint metadata for a step."""

    required: bool = Field(
        default=True,
        description="When true, step execution requires an explicit approve/reject decision.",
    )
    prompt: Optional[str] = Field(
        default=None,
        description="Optional reviewer-facing prompt or policy context for this checkpoint.",
    )


class StepApprovalDecisionType(str, Enum):
    """Allowed approval decisions for HITL-gated steps."""

    APPROVE = "approve"
    REJECT = "reject"


class StepApprovalDecision(BaseModel):
    """Approval decision payload supplied at macro execution time."""

    decision: StepApprovalDecisionType = Field(
        ...,
        description="approve | reject",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Required when decision=reject. Optional reviewer note when decision=approve.",
    )

    @model_validator(mode="after")
    def validate_reason(self) -> "StepApprovalDecision":
        if self.decision == StepApprovalDecisionType.REJECT:
            if not self.reason or not self.reason.strip():
                raise ValueError("reject decisions require a non-empty reason")
        return self


class ToolCall(BaseModel):
    """Represents a single tool execution requested by the LLM."""
    tool_name: str = Field(..., description="The hashed ID or name of the tool to run.")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="The arguments for the tool. Can include pointer_ids.")
    step_id: str = Field(..., description="A unique ID for this step so downstream tools can reference it.")
    branching: Optional["BranchingRule"] = Field(
        default=None,
        description="Optional conditional branching config for this step.",
    )
    approval: Optional[StepApprovalCheckpoint] = Field(
        default=None,
        description="Optional human approval checkpoint for this step.",
    )


class BranchingRule(BaseModel):
    """Conditional branch routing metadata for a macro step."""

    condition: str = Field(
        ...,
        description="Condition expression evaluated against prior step outputs/metadata.",
    )
    true_target_step_ids: List[str] = Field(
        default_factory=list,
        description="Step IDs to execute when condition evaluates true.",
    )
    false_target_step_ids: List[str] = Field(
        default_factory=list,
        description="Step IDs to execute when condition evaluates false.",
    )
    fallback_target_step_ids: List[str] = Field(
        default_factory=list,
        description="Fallback path step IDs when primary branch execution fails.",
    )
    allow_early_exit: bool = Field(
        default=False,
        description="If true, branch resolution may terminate the remaining DAG.",
    )

    @model_validator(mode="after")
    def validate_branch_rule(self) -> "BranchingRule":
        if not self.condition.strip():
            raise ValueError("branching condition cannot be empty")

        has_targets = bool(
            self.true_target_step_ids
            or self.false_target_step_ids
            or self.fallback_target_step_ids
        )
        if not has_targets and not self.allow_early_exit:
            raise ValueError(
                "branching rule requires at least one branch target or allow_early_exit=true"
            )

        return self


ToolCall.model_rebuild()


class RetryPolicy(BaseModel):
    """Retry policy for tool execution failures."""

    max_attempts: int = Field(default=3, ge=1, description="Maximum number of attempts per step.")
    initial_delay_seconds: float = Field(default=0.25, ge=0.0, description="Initial backoff delay in seconds.")
    backoff_multiplier: float = Field(default=2.0, ge=1.0, description="Backoff multiplier per retry.")
    retryable_error_types: List[str] = Field(
        default_factory=lambda: ["RuntimeError", "TimeoutError", "ConnectionError"],
        description="Exception class names that should trigger retries.",
    )


class ToolExecutionLimit(BaseModel):
    """Concurrency/rate limits for a single tool."""

    max_concurrency: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum concurrent in-flight calls allowed for this tool.",
    )
    requests_per_second: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Token refill rate for this tool's request bucket.",
    )
    burst_capacity: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum burst tokens for the tool bucket.",
    )

    @model_validator(mode="after")
    def validate_bucket_contract(self) -> "ToolExecutionLimit":
        if self.burst_capacity is not None and self.requests_per_second is None:
            raise ValueError("burst_capacity requires requests_per_second")
        return self


class ExecutionLimits(BaseModel):
    """Executor-wide and per-tool concurrency/rate limiting configuration."""

    max_global_concurrency: int = Field(
        default=8,
        ge=1,
        description="Maximum concurrent in-flight tool executions across the whole run.",
    )
    global_requests_per_second: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Global token bucket refill rate for all tool attempts.",
    )
    global_burst_capacity: Optional[int] = Field(
        default=None,
        ge=1,
        description="Global token bucket burst capacity. Requires global_requests_per_second.",
    )
    per_tool: Dict[str, ToolExecutionLimit] = Field(
        default_factory=dict,
        description="Per-tool overrides keyed by resolved tool name.",
    )

    @model_validator(mode="after")
    def validate_execution_limits(self) -> "ExecutionLimits":
        if self.global_burst_capacity is not None and self.global_requests_per_second is None:
            raise ValueError("global_burst_capacity requires global_requests_per_second")
        for tool_name in self.per_tool:
            if not tool_name.strip():
                raise ValueError("per_tool keys must be non-empty tool names")
        return self


class ExecutionTraceEventType(str, Enum):
    """Lifecycle states emitted during step execution."""

    REPLAYED = "replayed"
    QUEUED = "queued"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    STARTED = "started"
    RETRIED = "retried"
    FAILED = "failed"
    COMPLETED = "completed"


class ExecutionTraceEvent(BaseModel):
    """Structured step-level execution trace event."""

    run_id: str = Field(..., description="Unique run ID for the macro execution.")
    step_id: str = Field(..., description="Step ID this event belongs to.")
    tool_name: str = Field(..., description="Tool name/hash executed for this step.")
    event_type: ExecutionTraceEventType = Field(..., description="Execution lifecycle event type.")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp for this event.",
    )
    attempt: int = Field(default=1, ge=1, description="Attempt number at event emission.")
    resolved_arguments: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Resolved runtime arguments after pointer dereference.",
    )
    input_pointer_ids: Optional[Dict[str, str]] = Field(
        default=None,
        description="Argument key to pointer-id map for referenced pointer inputs.",
    )
    output_pointer_id: Optional[str] = Field(
        default=None,
        description="Pointer ID produced on completion events.",
    )
    duration_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Step duration in milliseconds where available.",
    )
    retry_delay_seconds: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Backoff delay before next retry for retried events.",
    )
    error: Optional[ToolErrorPayload] = Field(
        default=None,
        description="Structured error payload for failed/retried events.",
    )
    actor_id: Optional[str] = Field(
        default=None,
        description="Actor ID associated with the run-affecting operation for this event.",
    )
    actor_scopes: Optional[List[str]] = Field(
        default=None,
        description="Authorization scopes granted to the actor when the event was emitted.",
    )
    operation: Optional[str] = Field(
        default=None,
        description="Run-affecting operation context for this event: execute | resume.",
    )

    @model_validator(mode="after")
    def validate_event_contract(self) -> "ExecutionTraceEvent":
        if self.actor_scopes is not None:
            normalized_scopes = sorted({scope.strip() for scope in self.actor_scopes if scope.strip()})
            if not normalized_scopes:
                raise ValueError("actor_scopes must include at least one non-empty scope when provided")
            self.actor_scopes = normalized_scopes

        if self.operation is not None and self.operation not in {"execute", "resume"}:
            raise ValueError("operation must be one of: execute, resume")

        if self.event_type == ExecutionTraceEventType.REPLAYED:
            if not self.output_pointer_id:
                raise ValueError("replayed events must include output_pointer_id")
            if self.error:
                raise ValueError("replayed events cannot include error")

        if self.event_type == ExecutionTraceEventType.QUEUED:
            if self.output_pointer_id or self.error or self.duration_ms is not None:
                raise ValueError("queued events cannot include output_pointer_id, error, or duration_ms")

        if self.event_type == ExecutionTraceEventType.APPROVAL_REQUIRED:
            if self.output_pointer_id or self.error or self.duration_ms is not None:
                raise ValueError(
                    "approval_required events cannot include output_pointer_id, error, or duration_ms"
                )

        if self.event_type == ExecutionTraceEventType.APPROVED:
            if self.output_pointer_id or self.error or self.duration_ms is not None:
                raise ValueError(
                    "approved events cannot include output_pointer_id, error, or duration_ms"
                )

        if self.event_type == ExecutionTraceEventType.REJECTED:
            if not self.error:
                raise ValueError("rejected events must include error")
            if self.output_pointer_id:
                raise ValueError("rejected events cannot include output_pointer_id")

        if self.event_type == ExecutionTraceEventType.STARTED:
            if self.output_pointer_id or self.error:
                raise ValueError("started events cannot include output_pointer_id or error")

        if self.event_type == ExecutionTraceEventType.RETRIED:
            if not self.error:
                raise ValueError("retried events must include error")
            if self.retry_delay_seconds is None:
                raise ValueError("retried events must include retry_delay_seconds")
            if self.output_pointer_id:
                raise ValueError("retried events cannot include output_pointer_id")

        if self.event_type == ExecutionTraceEventType.FAILED:
            if not self.error:
                raise ValueError("failed events must include error")
            if self.output_pointer_id:
                raise ValueError("failed events cannot include output_pointer_id")

        if self.event_type == ExecutionTraceEventType.COMPLETED:
            if not self.output_pointer_id:
                raise ValueError("completed events must include output_pointer_id")
            if self.error:
                raise ValueError("completed events cannot include error")

        return self


class MemoryStrategy(str, Enum):
    """Conversation memory strategy per session."""

    FULL = "full"
    WINDOW = "window"
    SUMMARY = "summary"


class ConversationSession(BaseModel):
    """Persistent conversation session metadata."""

    session_id: str = Field(..., description="Unique conversation session ID.")
    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when session was created.",
    )
    updated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when session was last updated.",
    )
    memory_strategy: MemoryStrategy = Field(
        default=MemoryStrategy.FULL,
        description="Conversation memory strategy for this session.",
    )
    window_turn_limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Turn limit used for window strategy sessions.",
    )
    summary_text: Optional[str] = Field(
        default=None,
        description="Persisted rolling summary for summary strategy sessions.",
    )
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional session metadata.")


class ConversationTurn(BaseModel):
    """Persistent turn data for a conversation session."""

    turn_id: str = Field(..., description="Unique turn ID.")
    session_id: str = Field(..., description="Parent conversation session ID.")
    role: str = Field(..., description="speaker role: user | assistant | system")
    content: str = Field(..., description="Turn content text.")
    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when turn was recorded.",
    )
    pointer_ids: List[str] = Field(
        default_factory=list,
        description="Pointer IDs referenced in this turn.",
    )
    macro_run_id: Optional[str] = Field(
        default=None,
        description="Execution run ID associated with this turn if applicable.",
    )
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional turn metadata.")

    @model_validator(mode="after")
    def validate_role(self) -> "ConversationTurn":
        if self.role not in {"user", "assistant", "system"}:
            raise ValueError("role must be one of: user, assistant, system")
        return self


class BatchedMacroRequest(BaseModel):
    """The payload the LLM sends to execute multiple tools in one round-trip."""
    steps: List[ToolCall] = Field(..., description="An ordered list of tools to execute.")
    return_final_state_only: bool = Field(
        default=True, 
        description="If true, only return the pointer/summary of the very last step."
    )
    retry_policy: RetryPolicy = Field(
        default_factory=RetryPolicy,
        description="Retry policy applied by executor for tool execution errors.",
    )
    execution_limits: Optional[ExecutionLimits] = Field(
        default=None,
        description="Optional concurrency/rate limit settings for this macro run.",
    )
    approvals: Dict[str, StepApprovalDecision] = Field(
        default_factory=dict,
        description="Optional approve/reject decisions keyed by step_id for approval-gated steps.",
    )

    @model_validator(mode="after")
    def validate_branch_targets(self) -> "BatchedMacroRequest":
        step_ids = {step.step_id for step in self.steps}
        step_by_id: Dict[str, ToolCall] = {step.step_id: step for step in self.steps}
        for step in self.steps:
            if not step.branching:
                continue
            for target in (
                step.branching.true_target_step_ids
                + step.branching.false_target_step_ids
                + step.branching.fallback_target_step_ids
            ):
                if target not in step_ids:
                    raise ValueError(
                        f"branch target '{target}' in step '{step.step_id}' is not a valid step_id"
                    )
                if target == step.step_id:
                    raise ValueError(
                        f"branch target '{target}' in step '{step.step_id}' cannot self-reference"
                    )

        for approval_step_id in self.approvals.keys():
            if approval_step_id not in step_ids:
                raise ValueError(
                    f"approval decision step_id '{approval_step_id}' is not a valid step_id"
                )
            step = step_by_id[approval_step_id]
            if not step.approval or not step.approval.required:
                raise ValueError(
                    f"approval decision provided for step '{approval_step_id}' "
                    "without approval.required=true"
                )
        return self


class WorkflowEdgeKind(str, Enum):
    """Edge classification for persisted workflow graphs."""

    DEPENDENCY = "dependency"
    BRANCH_TRUE = "branch_true"
    BRANCH_FALSE = "branch_false"
    BRANCH_FALLBACK = "branch_fallback"


class WorkflowGraphNode(BaseModel):
    """Visual editor node wrapping an executable tool step."""

    node_id: str = Field(..., description="Stable node ID in the persisted graph.")
    step: ToolCall = Field(..., description="Executable step mapped to macro format.")
    label: Optional[str] = Field(default=None, description="Optional UI label for the node.")
    position_x: float = Field(default=0.0, description="Canvas X coordinate.")
    position_y: float = Field(default=0.0, description="Canvas Y coordinate.")

    @model_validator(mode="after")
    def validate_node(self) -> "WorkflowGraphNode":
        if not self.node_id.strip():
            raise ValueError("node_id cannot be empty")
        return self


class WorkflowGraphEdge(BaseModel):
    """Directed edge between graph nodes."""

    source_node_id: str = Field(..., description="Source node ID.")
    target_node_id: str = Field(..., description="Target node ID.")
    kind: WorkflowEdgeKind = Field(
        default=WorkflowEdgeKind.DEPENDENCY,
        description="Edge semantics for dependency/branch routing.",
    )

    @model_validator(mode="after")
    def validate_edge(self) -> "WorkflowGraphEdge":
        if self.source_node_id == self.target_node_id:
            raise ValueError("workflow edges cannot self-reference a node")
        return self


class PersistedWorkflowGraph(BaseModel):
    """Persisted workflow graph schema for visual DAG editing."""

    workflow_id: str = Field(..., description="Stable workflow graph ID.")
    version: int = Field(default=1, ge=1, description="Schema version for persisted graph data.")
    nodes: List[WorkflowGraphNode] = Field(..., description="Graph nodes.")
    edges: List[WorkflowGraphEdge] = Field(default_factory=list, description="Graph edges.")
    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the workflow graph was created.",
    )
    updated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the workflow graph was last updated.",
    )
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional graph metadata.")

    @model_validator(mode="after")
    def validate_graph(self) -> "PersistedWorkflowGraph":
        if not self.workflow_id.strip():
            raise ValueError("workflow_id cannot be empty")
        if not self.nodes:
            raise ValueError("workflow graph requires at least one node")

        node_ids: Dict[str, WorkflowGraphNode] = {}
        step_ids: set[str] = set()
        node_id_to_step_id: Dict[str, str] = {}
        for node in self.nodes:
            if node.node_id in node_ids:
                raise ValueError(f"duplicate node_id '{node.node_id}' in workflow graph")
            if node.step.step_id in step_ids:
                raise ValueError(f"duplicate step_id '{node.step.step_id}' in workflow graph nodes")
            node_ids[node.node_id] = node
            step_ids.add(node.step.step_id)
            node_id_to_step_id[node.node_id] = node.step.step_id

        branch_edges_by_source: Dict[str, Dict[WorkflowEdgeKind, set[str]]] = defaultdict(
            lambda: {
                WorkflowEdgeKind.BRANCH_TRUE: set(),
                WorkflowEdgeKind.BRANCH_FALSE: set(),
                WorkflowEdgeKind.BRANCH_FALLBACK: set(),
            }
        )
        dependency_edges: List[WorkflowGraphEdge] = []

        for edge in self.edges:
            if edge.source_node_id not in node_ids:
                raise ValueError(f"edge source '{edge.source_node_id}' is not a valid node_id")
            if edge.target_node_id not in node_ids:
                raise ValueError(f"edge target '{edge.target_node_id}' is not a valid node_id")

            if edge.kind == WorkflowEdgeKind.DEPENDENCY:
                dependency_edges.append(edge)
                continue

            source_node = node_ids[edge.source_node_id]
            if source_node.step.branching is None:
                raise ValueError(
                    f"branch edge from '{edge.source_node_id}' requires source step branching metadata"
                )
            branch_edges_by_source[edge.source_node_id][edge.kind].add(
                node_id_to_step_id[edge.target_node_id]
            )

        for node in self.nodes:
            if not node.step.branching:
                continue
            expected = {
                WorkflowEdgeKind.BRANCH_TRUE: set(node.step.branching.true_target_step_ids),
                WorkflowEdgeKind.BRANCH_FALSE: set(node.step.branching.false_target_step_ids),
                WorkflowEdgeKind.BRANCH_FALLBACK: set(node.step.branching.fallback_target_step_ids),
            }
            actual = branch_edges_by_source.get(node.node_id)
            if actual is None:
                actual = {
                    WorkflowEdgeKind.BRANCH_TRUE: set(),
                    WorkflowEdgeKind.BRANCH_FALSE: set(),
                    WorkflowEdgeKind.BRANCH_FALLBACK: set(),
                }
            for kind in (
                WorkflowEdgeKind.BRANCH_TRUE,
                WorkflowEdgeKind.BRANCH_FALSE,
                WorkflowEdgeKind.BRANCH_FALLBACK,
            ):
                if actual[kind] != expected[kind]:
                    raise ValueError(
                        f"branch edges for node '{node.node_id}' and kind '{kind.value}' "
                        "must exactly match branching target step_ids"
                    )

        self._validate_dependency_acyclic(node_ids=node_ids, dependency_edges=dependency_edges)
        return self

    @staticmethod
    def _validate_dependency_acyclic(
        node_ids: Dict[str, WorkflowGraphNode],
        dependency_edges: List[WorkflowGraphEdge],
    ) -> None:
        adjacency: Dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        in_degree: Dict[str, int] = {node_id: 0 for node_id in node_ids}
        for edge in dependency_edges:
            if edge.target_node_id not in adjacency[edge.source_node_id]:
                adjacency[edge.source_node_id].add(edge.target_node_id)
                in_degree[edge.target_node_id] += 1

        ordered = []
        frontier = sorted(node_id for node_id, degree in in_degree.items() if degree == 0)
        while frontier:
            current = frontier.pop(0)
            ordered.append(current)
            for target in sorted(adjacency[current]):
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    frontier.append(target)
            frontier.sort()

        if len(ordered) != len(node_ids):
            raise ValueError("dependency edges contain a cycle; workflow graph must be acyclic")

    def to_batched_macro_request(
        self,
        return_final_state_only: bool = True,
        retry_policy: Optional[RetryPolicy] = None,
        execution_limits: Optional[ExecutionLimits] = None,
    ) -> BatchedMacroRequest:
        node_map = {node.node_id: node for node in self.nodes}
        adjacency: Dict[str, set[str]] = {node.node_id: set() for node in self.nodes}
        in_degree: Dict[str, int] = {node.node_id: 0 for node in self.nodes}

        for edge in self.edges:
            if edge.kind != WorkflowEdgeKind.DEPENDENCY:
                continue
            if edge.target_node_id not in adjacency[edge.source_node_id]:
                adjacency[edge.source_node_id].add(edge.target_node_id)
                in_degree[edge.target_node_id] += 1

        frontier = sorted(node_id for node_id, degree in in_degree.items() if degree == 0)
        ordered_node_ids: List[str] = []
        while frontier:
            current = frontier.pop(0)
            ordered_node_ids.append(current)
            for target in sorted(adjacency[current]):
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    frontier.append(target)
            frontier.sort()

        if len(ordered_node_ids) != len(self.nodes):
            raise ValueError("cannot compile workflow graph with cyclic dependency edges")

        steps = [node_map[node_id].step.model_copy(deep=True) for node_id in ordered_node_ids]
        payload: Dict[str, Any] = {
            "steps": steps,
            "return_final_state_only": return_final_state_only,
        }
        if retry_policy is not None:
            payload["retry_policy"] = retry_policy
        if execution_limits is not None:
            payload["execution_limits"] = execution_limits
        return BatchedMacroRequest(**payload)

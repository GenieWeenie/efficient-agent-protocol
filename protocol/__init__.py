# protocol/__init__.py
"""Deprecated namespace. Use ``eap.protocol`` instead."""
from __future__ import annotations

import importlib
import warnings

__all__ = [
    "PointerResponse",
    "PersistedWorkflowGraph",
    "ToolErrorPayload",
    "ToolCall",
    "BranchingRule",
    "RetryPolicy",
    "MemoryStrategy",
    "ConversationSession",
    "ConversationTurn",
    "StepApprovalCheckpoint",
    "StepApprovalDecisionType",
    "StepApprovalDecision",
    "ExecutionTraceEventType",
    "ExecutionTraceEvent",
    "ToolExecutionLimit",
    "ExecutionLimits",
    "BatchedMacroRequest",
    "WorkflowEdgeKind",
    "WorkflowGraphEdge",
    "WorkflowGraphNode",
    "StateManager",
    "configure_logging",
    "LLMClientSettings",
    "ToolLimitSettings",
    "ExecutorLimitSettings",
    "EAPSettings",
    "load_settings",
    "PointerStoreBackend",
    "PostgresPointerStore",
    "RedisPointerStore",
    "SQLitePointerStore",
]

_SUBMODULE_MAP: dict[str, tuple[str, str]] = {
    "BatchedMacroRequest": ("protocol.models", "BatchedMacroRequest"),
    "BranchingRule": ("protocol.models", "BranchingRule"),
    "ConversationSession": ("protocol.models", "ConversationSession"),
    "ConversationTurn": ("protocol.models", "ConversationTurn"),
    "ExecutionLimits": ("protocol.models", "ExecutionLimits"),
    "ExecutionTraceEvent": ("protocol.models", "ExecutionTraceEvent"),
    "ExecutionTraceEventType": ("protocol.models", "ExecutionTraceEventType"),
    "MemoryStrategy": ("protocol.models", "MemoryStrategy"),
    "PersistedWorkflowGraph": ("protocol.models", "PersistedWorkflowGraph"),
    "PointerResponse": ("protocol.models", "PointerResponse"),
    "RetryPolicy": ("protocol.models", "RetryPolicy"),
    "StepApprovalCheckpoint": ("protocol.models", "StepApprovalCheckpoint"),
    "StepApprovalDecision": ("protocol.models", "StepApprovalDecision"),
    "StepApprovalDecisionType": ("protocol.models", "StepApprovalDecisionType"),
    "ToolCall": ("protocol.models", "ToolCall"),
    "ToolErrorPayload": ("protocol.models", "ToolErrorPayload"),
    "ToolExecutionLimit": ("protocol.models", "ToolExecutionLimit"),
    "WorkflowEdgeKind": ("protocol.models", "WorkflowEdgeKind"),
    "WorkflowGraphEdge": ("protocol.models", "WorkflowGraphEdge"),
    "WorkflowGraphNode": ("protocol.models", "WorkflowGraphNode"),
    "StateManager": ("protocol.state_manager", "StateManager"),
    "configure_logging": ("protocol.logging_config", "configure_logging"),
    "EAPSettings": ("protocol.settings", "EAPSettings"),
    "ExecutorLimitSettings": ("protocol.settings", "ExecutorLimitSettings"),
    "LLMClientSettings": ("protocol.settings", "LLMClientSettings"),
    "ToolLimitSettings": ("protocol.settings", "ToolLimitSettings"),
    "load_settings": ("protocol.settings", "load_settings"),
    "PointerStoreBackend": ("protocol.storage", "PointerStoreBackend"),
    "PostgresPointerStore": ("protocol.storage", "PostgresPointerStore"),
    "RedisPointerStore": ("protocol.storage", "RedisPointerStore"),
    "SQLitePointerStore": ("protocol.storage", "SQLitePointerStore"),
}


def __getattr__(name: str) -> object:
    if name in _SUBMODULE_MAP:
        module_path, attr = _SUBMODULE_MAP[name]
        warnings.warn(
            f"Importing '{name}' from 'protocol' is deprecated and will be removed "
            "in v2.0. Use 'from eap.protocol import " + name + "' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

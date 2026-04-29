"""Compatibility namespace. Use ``eap.protocol`` instead."""
from __future__ import annotations

import importlib
import warnings

__all__ = ['BatchedMacroRequest', 'BranchingRule', 'ConversationSession', 'ConversationTurn', 'ExecutionLimits', 'ExecutionTraceEvent', 'ExecutionTraceEventType', 'MemoryStrategy', 'PersistedWorkflowGraph', 'PointerResponse', 'RetryPolicy', 'StepApprovalCheckpoint', 'StepApprovalDecision', 'StepApprovalDecisionType', 'ToolCall', 'ToolErrorPayload', 'ToolExecutionLimit', 'WorkflowEdgeKind', 'WorkflowGraphEdge', 'WorkflowGraphNode', 'StateManager', 'configure_logging', 'EAPSettings', 'ExecutorLimitSettings', 'LLMClientSettings', 'ToolLimitSettings', 'load_settings', 'PointerStoreBackend', 'PostgresPointerStore', 'RedisPointerStore', 'SQLitePointerStore']

_SUBMODULE_MAP: dict[str, tuple[str, str]] = {
    'BatchedMacroRequest': ('eap.protocol.models', 'BatchedMacroRequest'),
    'BranchingRule': ('eap.protocol.models', 'BranchingRule'),
    'ConversationSession': ('eap.protocol.models', 'ConversationSession'),
    'ConversationTurn': ('eap.protocol.models', 'ConversationTurn'),
    'ExecutionLimits': ('eap.protocol.models', 'ExecutionLimits'),
    'ExecutionTraceEvent': ('eap.protocol.models', 'ExecutionTraceEvent'),
    'ExecutionTraceEventType': ('eap.protocol.models', 'ExecutionTraceEventType'),
    'MemoryStrategy': ('eap.protocol.models', 'MemoryStrategy'),
    'PersistedWorkflowGraph': ('eap.protocol.models', 'PersistedWorkflowGraph'),
    'PointerResponse': ('eap.protocol.models', 'PointerResponse'),
    'RetryPolicy': ('eap.protocol.models', 'RetryPolicy'),
    'StepApprovalCheckpoint': ('eap.protocol.models', 'StepApprovalCheckpoint'),
    'StepApprovalDecision': ('eap.protocol.models', 'StepApprovalDecision'),
    'StepApprovalDecisionType': ('eap.protocol.models', 'StepApprovalDecisionType'),
    'ToolCall': ('eap.protocol.models', 'ToolCall'),
    'ToolErrorPayload': ('eap.protocol.models', 'ToolErrorPayload'),
    'ToolExecutionLimit': ('eap.protocol.models', 'ToolExecutionLimit'),
    'WorkflowEdgeKind': ('eap.protocol.models', 'WorkflowEdgeKind'),
    'WorkflowGraphEdge': ('eap.protocol.models', 'WorkflowGraphEdge'),
    'WorkflowGraphNode': ('eap.protocol.models', 'WorkflowGraphNode'),
    'StateManager': ('eap.protocol.state_manager', 'StateManager'),
    'configure_logging': ('eap.protocol.logging_config', 'configure_logging'),
    'EAPSettings': ('eap.protocol.settings', 'EAPSettings'),
    'ExecutorLimitSettings': ('eap.protocol.settings', 'ExecutorLimitSettings'),
    'LLMClientSettings': ('eap.protocol.settings', 'LLMClientSettings'),
    'ToolLimitSettings': ('eap.protocol.settings', 'ToolLimitSettings'),
    'load_settings': ('eap.protocol.settings', 'load_settings'),
    'PointerStoreBackend': ('eap.protocol.storage', 'PointerStoreBackend'),
    'PostgresPointerStore': ('eap.protocol.storage', 'PostgresPointerStore'),
    'RedisPointerStore': ('eap.protocol.storage', 'RedisPointerStore'),
    'SQLitePointerStore': ('eap.protocol.storage', 'SQLitePointerStore')
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

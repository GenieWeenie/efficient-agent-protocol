# agent/__init__.py
"""Deprecated namespace. Use ``eap.agent`` instead."""
from __future__ import annotations

import importlib
import warnings

__all__ = [
    "MacroCompiler",
    "WorkflowGraphCompiler",
    "AgentClient",
    "ProviderMessage",
    "CompletionRequest",
    "CompletionResponse",
    "LLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "create_provider",
]

_SUBMODULE_MAP: dict[str, tuple[str, str]] = {
    "MacroCompiler": ("agent.compiler", "MacroCompiler"),
    "WorkflowGraphCompiler": ("agent.compiler", "WorkflowGraphCompiler"),
    "AgentClient": ("agent.agent_client", "AgentClient"),
    "ProviderMessage": ("agent.providers", "ProviderMessage"),
    "CompletionRequest": ("agent.providers", "CompletionRequest"),
    "CompletionResponse": ("agent.providers", "CompletionResponse"),
    "LLMProvider": ("agent.providers", "LLMProvider"),
    "OpenAIProvider": ("agent.providers", "OpenAIProvider"),
    "AnthropicProvider": ("agent.providers", "AnthropicProvider"),
    "GoogleProvider": ("agent.providers", "GoogleProvider"),
    "create_provider": ("agent.providers", "create_provider"),
}


def __getattr__(name: str) -> object:
    if name in _SUBMODULE_MAP:
        module_path, attr = _SUBMODULE_MAP[name]
        warnings.warn(
            f"Importing '{name}' from 'agent' is deprecated and will be removed "
            "in v2.0. Use 'from eap.agent import " + name + "' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

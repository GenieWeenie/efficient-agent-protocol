# environment/__init__.py
"""Deprecated namespace. Use ``eap.environment`` instead."""
from __future__ import annotations

import importlib
import warnings

__all__ = [
    "AsyncLocalExecutor",
    "DistributedCoordinator",
    "ToolRegistry",
    "ToolDefinition",
    "InputValidationError",
    "PluginManifestError",
    "PluginLoadError",
    "DEFAULT_PLUGIN_ENTRYPOINT_GROUP",
    "discover_plugin_entry_points",
    "load_plugins_into_registry",
]

_SUBMODULE_MAP: dict[str, tuple[str, str]] = {
    "AsyncLocalExecutor": ("environment.executor", "AsyncLocalExecutor"),
    "DistributedCoordinator": ("environment.distributed_executor", "DistributedCoordinator"),
    "ToolRegistry": ("environment.tool_registry", "ToolRegistry"),
    "ToolDefinition": ("environment.tool_registry", "ToolDefinition"),
    "InputValidationError": ("environment.tool_registry", "InputValidationError"),
    "PluginManifestError": ("environment.tool_registry", "PluginManifestError"),
    "PluginLoadError": ("environment.plugin_loader", "PluginLoadError"),
    "DEFAULT_PLUGIN_ENTRYPOINT_GROUP": ("environment.plugin_loader", "DEFAULT_PLUGIN_ENTRYPOINT_GROUP"),
    "discover_plugin_entry_points": ("environment.plugin_loader", "discover_plugin_entry_points"),
    "load_plugins_into_registry": ("environment.plugin_loader", "load_plugins_into_registry"),
}


def __getattr__(name: str) -> object:
    if name in _SUBMODULE_MAP:
        module_path, attr = _SUBMODULE_MAP[name]
        warnings.warn(
            f"Importing '{name}' from 'environment' is deprecated and will be removed "
            "in v2.0. Use 'from eap.environment import " + name + "' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

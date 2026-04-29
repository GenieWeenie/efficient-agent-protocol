"""Compatibility namespace. Use ``eap.environment`` instead."""
from __future__ import annotations

import importlib
import warnings

__all__ = ['AsyncLocalExecutor', 'DistributedCoordinator', 'ToolRegistry', 'ToolDefinition', 'InputValidationError', 'PluginManifestError', 'PluginLoadError', 'DEFAULT_PLUGIN_ENTRYPOINT_GROUP', 'discover_plugin_entry_points', 'load_plugins_into_registry']

_SUBMODULE_MAP: dict[str, tuple[str, str]] = {
    'AsyncLocalExecutor': ('eap.environment.executor', 'AsyncLocalExecutor'),
    'DistributedCoordinator': ('eap.environment.distributed_executor', 'DistributedCoordinator'),
    'ToolRegistry': ('eap.environment.tool_registry', 'ToolRegistry'),
    'ToolDefinition': ('eap.environment.tool_registry', 'ToolDefinition'),
    'InputValidationError': ('eap.environment.tool_registry', 'InputValidationError'),
    'PluginManifestError': ('eap.environment.tool_registry', 'PluginManifestError'),
    'PluginLoadError': ('eap.environment.plugin_loader', 'PluginLoadError'),
    'DEFAULT_PLUGIN_ENTRYPOINT_GROUP': ('eap.environment.plugin_loader', 'DEFAULT_PLUGIN_ENTRYPOINT_GROUP'),
    'discover_plugin_entry_points': ('eap.environment.plugin_loader', 'discover_plugin_entry_points'),
    'load_plugins_into_registry': ('eap.environment.plugin_loader', 'load_plugins_into_registry')
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

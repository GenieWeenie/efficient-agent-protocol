import logging
from importlib import metadata
from typing import Any, Callable, Dict, List

from environment.tool_registry import (
    DEFAULT_PLUGIN_ENTRYPOINT_GROUP,
    PluginManifestError,
    ToolRegistry,
)

logger = logging.getLogger("eap.environment.plugin_loader")


class PluginLoadError(RuntimeError):
    """Raised when plugin discovery/loading fails in strict mode."""


def discover_plugin_entry_points(
    group: str = DEFAULT_PLUGIN_ENTRYPOINT_GROUP,
    entry_points_fn: Callable[[], Any] = None,
) -> List[Any]:
    """Discover plugin entry points with compatibility across Python metadata APIs."""
    provider = entry_points_fn or metadata.entry_points
    discovered = provider()

    if hasattr(discovered, "select"):
        return list(discovered.select(group=group))
    if isinstance(discovered, dict):
        return list(discovered.get(group, []))

    entry_points = []
    for entry_point in discovered:
        entry_point_group = getattr(entry_point, "group", group)
        if entry_point_group == group:
            entry_points.append(entry_point)
    return entry_points


def _resolve_manifest_from_entry_point(entry_point: Any) -> Dict[str, Any]:
    loaded = entry_point.load()
    manifest = loaded() if callable(loaded) else loaded
    if not isinstance(manifest, dict):
        raise PluginManifestError(
            f"Plugin entry point '{getattr(entry_point, 'name', 'unknown')}' must resolve to a manifest object."
        )
    if not manifest.get("plugin_name"):
        manifest = dict(manifest)
        manifest["plugin_name"] = getattr(entry_point, "name", "unnamed_plugin")
    return manifest


def load_plugins_into_registry(
    registry: ToolRegistry,
    group: str = DEFAULT_PLUGIN_ENTRYPOINT_GROUP,
    strict: bool = False,
    entry_points_fn: Callable[[], Any] = None,
) -> Dict[str, Any]:
    """
    Load all discovered plugin manifests into the provided registry.

    Returns:
      {
        "group": "...",
        "loaded_plugins": [plugin_name, ...],
        "loaded_tools": [tool_name, ...],
        "failed_plugins": [{"entry_point": "...", "error": "..."}]
      }
    """
    report = {
        "group": group,
        "loaded_plugins": [],
        "loaded_tools": [],
        "failed_plugins": [],
    }

    for entry_point in discover_plugin_entry_points(group=group, entry_points_fn=entry_points_fn):
        entry_point_name = getattr(entry_point, "name", str(entry_point))
        try:
            manifest = _resolve_manifest_from_entry_point(entry_point)
            tool_names = registry.register_plugin_manifest(
                manifest,
                source=f"entry_point:{entry_point_name}",
            )
            report["loaded_plugins"].append(manifest["plugin_name"])
            report["loaded_tools"].extend(tool_names)
        except Exception as exc:
            logger.warning(
                "plugin load failed",
                extra={"entry_point": entry_point_name, "group": group, "error": str(exc)},
            )
            failure = {"entry_point": entry_point_name, "error": str(exc)}
            report["failed_plugins"].append(failure)
            if strict:
                raise PluginLoadError(
                    f"Failed to load plugin entry point '{entry_point_name}': {str(exc)}"
                ) from exc

    return report


__all__ = [
    "PluginLoadError",
    "discover_plugin_entry_points",
    "load_plugins_into_registry",
    "DEFAULT_PLUGIN_ENTRYPOINT_GROUP",
]

# Plugin Specification

This document defines the third-party tool plugin contract for EAP.

## Discovery

- Discovery mechanism: Python entry points via `importlib.metadata.entry_points()`.
- Entry point group: `eap.tool_plugins`.
- Entry point target:
  - either a callable returning a plugin manifest object
  - or a manifest object directly

## Plugin manifest contract

Each plugin must resolve to a manifest object with this shape:

```python
{
  "plugin_name": "sample_plugin",
  "version": "0.1.0",  # optional
  "tools": [
    {
      "name": "tool_name",
      "function": callable,
      "schema": {
        "name": "tool_name",
        "description": "...",  # optional
        "parameters": {
          "type": "object",
          "properties": {...},
          "required": [...],
          "additionalProperties": False,  # recommended
        },
      },
    },
  ],
}
```

## Tool schema requirements

For each plugin tool:
- `schema["name"]` must match tool `name`
- `schema["parameters"]` must be an object
- `schema["parameters"]["type"]` must be `object` (or omitted)
- `schema["parameters"]["properties"]` must be an object
- `schema["parameters"]["required"]` must be a list of strings (if present)
- each field in `required` must exist in `properties`
- `additionalProperties` must be boolean if provided

## Runtime loading and safety

EAP exposes two loading modes:
- Non-strict: plugin load failures are captured in a failure report and startup continues.
- Strict: first plugin load failure raises `PluginLoadError`.

Load result contract:

```python
{
  "group": "eap.tool_plugins",
  "loaded_plugins": ["..."],
  "loaded_tools": ["..."],
  "failed_plugins": [{"entry_point": "...", "error": "..."}],
}
```

## Registry integration

`ToolRegistry` supports:
- `register_plugin_manifest(manifest, source=...)`
- `load_plugins(group=..., strict=..., entry_points_fn=...)`

This enables both real entry-point discovery and deterministic test injection.

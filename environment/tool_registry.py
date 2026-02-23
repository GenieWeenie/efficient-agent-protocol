# environment/tool_registry.py
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List


class InputValidationError(ValueError):
    """Raised when tool arguments do not satisfy schema requirements."""


class PluginManifestError(ValueError):
    """Raised when plugin-provided manifests do not satisfy the tool contract."""


DEFAULT_PLUGIN_ENTRYPOINT_GROUP = "eap.tool_plugins"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    func: Callable
    schema: Dict[str, Any]


class ToolRegistry:
    """
    Manages available tools, stores their verbose JSON schemas, 
    and generates lightweight hashes to save LLM context tokens.
    """
    def __init__(
        self,
        auto_load_plugins: bool = False,
        plugin_group: str = DEFAULT_PLUGIN_ENTRYPOINT_GROUP,
        strict_plugin_loading: bool = False,
    ):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, dict] = {}
        self._hashes: Dict[str, str] = {}
        if auto_load_plugins:
            self.load_plugins(group=plugin_group, strict=strict_plugin_loading)

    def register(self, name: str, func: Callable, schema: dict):
        """Registers a tool and generates a unique hash based on its schema."""
        if not isinstance(name, str) or not name.strip():
            raise PluginManifestError("Tool name must be a non-empty string.")
        if not callable(func):
            raise PluginManifestError(f"Tool '{name}' function must be callable.")
        self.validate_schema_contract(name, schema)

        self._tools[name] = func
        self._schemas[name] = schema
        
        # Create a deterministic hash of the schema
        # If the schema changes, the hash changes automatically
        schema_str = json.dumps(schema, sort_keys=True)
        schema_hash = hashlib.md5(schema_str.encode()).hexdigest()[:8]
        
        hashed_name = f"{name}_{schema_hash}"
        self._hashes[name] = hashed_name

    def register_tool_definition(self, tool_definition: ToolDefinition) -> None:
        """Registers a validated tool definition object."""
        self.register(tool_definition.name, tool_definition.func, tool_definition.schema)

    @staticmethod
    def validate_schema_contract(tool_name: str, schema: Dict[str, Any]) -> None:
        """Validate schema structure required by EAP runtime and planner manifesting."""
        if not isinstance(schema, dict):
            raise PluginManifestError(f"Schema for tool '{tool_name}' must be an object.")
        schema_name = schema.get("name")
        if schema_name != tool_name:
            raise PluginManifestError(
                f"Schema name mismatch for tool '{tool_name}'. Expected '{tool_name}', got '{schema_name}'."
            )
        params = schema.get("parameters")
        if not isinstance(params, dict):
            raise PluginManifestError(f"Tool '{tool_name}' schema must include object 'parameters'.")
        if params.get("type") not in (None, "object"):
            raise PluginManifestError(f"Tool '{tool_name}' parameters type must be 'object'.")

        properties = params.get("properties")
        if properties is None or not isinstance(properties, dict):
            raise PluginManifestError(f"Tool '{tool_name}' parameters must include object 'properties'.")
        required = params.get("required", [])
        if not isinstance(required, list) or not all(isinstance(k, str) for k in required):
            raise PluginManifestError(f"Tool '{tool_name}' required field list must be a list of strings.")

        invalid_required = [field for field in required if field not in properties]
        if invalid_required:
            raise PluginManifestError(
                f"Tool '{tool_name}' required fields missing in properties: {invalid_required}."
            )

        additional = params.get("additionalProperties")
        if additional is not None and not isinstance(additional, bool):
            raise PluginManifestError(
                f"Tool '{tool_name}' additionalProperties must be a boolean when provided."
            )

    @staticmethod
    def _normalize_tool_definition(tool: Any) -> ToolDefinition:
        if isinstance(tool, ToolDefinition):
            return tool
        if not isinstance(tool, dict):
            raise PluginManifestError("Each plugin tool must be a ToolDefinition or an object payload.")

        name = tool.get("name")
        func = tool.get("function")
        schema = tool.get("schema")
        if not isinstance(name, str) or not name.strip():
            raise PluginManifestError("Each plugin tool must declare a non-empty string 'name'.")
        if not callable(func):
            raise PluginManifestError(f"Plugin tool '{name}' field 'function' must be callable.")
        if not isinstance(schema, dict):
            raise PluginManifestError(f"Plugin tool '{name}' field 'schema' must be an object.")
        return ToolDefinition(name=name, func=func, schema=schema)

    def register_plugin_manifest(self, manifest: Dict[str, Any], source: str = "unknown") -> List[str]:
        """
        Register all tools provided by a plugin manifest.

        Contract:
          {
            "plugin_name": "<string>",
            "version": "<optional string>",
            "tools": [
              {"name": "...", "function": <callable>, "schema": {...}}
            ]
          }
        """
        if not isinstance(manifest, dict):
            raise PluginManifestError(f"Plugin manifest from '{source}' must be an object.")

        plugin_name = manifest.get("plugin_name")
        tools = manifest.get("tools")
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise PluginManifestError(f"Plugin manifest from '{source}' missing non-empty 'plugin_name'.")
        if not isinstance(tools, list) or not tools:
            raise PluginManifestError(f"Plugin '{plugin_name}' must provide a non-empty 'tools' list.")

        registered = []
        for raw_tool in tools:
            tool = self._normalize_tool_definition(raw_tool)
            self.register(tool.name, tool.func, tool.schema)
            registered.append(tool.name)
        return registered

    def load_plugins(
        self,
        group: str = DEFAULT_PLUGIN_ENTRYPOINT_GROUP,
        strict: bool = False,
        entry_points_fn: Callable[[], Any] = None,
    ) -> Dict[str, Any]:
        """Discover and load plugin entry points into this registry."""
        from environment.plugin_loader import load_plugins_into_registry

        return load_plugins_into_registry(
            self,
            group=group,
            strict=strict,
            entry_points_fn=entry_points_fn,
        )

    def _sorted_by_tool_name(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        return {name: mapping[name] for name in sorted(mapping)}

    def _resolve_original_name(self, name_or_hash: str) -> str:
        for original_name, hashed_name in self._hashes.items():
            if name_or_hash in (original_name, hashed_name):
                return original_name
        raise ValueError(f"Tool reference '{name_or_hash}' not found in registry.")

    def get_tool(self, name_or_hash: str) -> Callable:
        """Retrieves a tool function by its original name or its hashed ID."""
        original_name = self._resolve_original_name(name_or_hash)
        return self._tools[original_name]

    def get_schema(self, name_or_hash: str) -> dict:
        """Retrieves a tool schema by original name or hash."""
        original_name = self._resolve_original_name(name_or_hash)
        return self._schemas[original_name]

    @staticmethod
    def _is_type_valid(expected_type: str, value: Any) -> bool:
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return (isinstance(value, (int, float)) and not isinstance(value, bool))
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            return isinstance(value, list)
        return True

    def validate_arguments(self, name_or_hash: str, arguments: Dict[str, Any]) -> None:
        """
        Validate arguments against the registered JSON schema (basic object checks).
        Raises InputValidationError on invalid payloads.
        """
        schema = self.get_schema(name_or_hash)
        params = schema.get("parameters", {})
        if params.get("type") not in (None, "object"):
            raise InputValidationError("Input validation failed: top-level parameters type must be object.")

        if not isinstance(arguments, dict):
            raise InputValidationError("Input validation failed: arguments payload must be an object.")

        properties = params.get("properties", {})
        required = params.get("required", [])
        additional_properties = params.get("additionalProperties", True)

        missing = [key for key in required if key not in arguments]
        if missing:
            raise InputValidationError(
                f"Input validation failed: missing required fields {missing} for tool '{schema.get('name', name_or_hash)}'."
            )

        if additional_properties is False:
            unknown_fields = [key for key in arguments if key not in properties]
            if unknown_fields:
                raise InputValidationError(
                    f"Input validation failed: unknown fields {unknown_fields} for tool '{schema.get('name', name_or_hash)}'."
                )

        for key, value in arguments.items():
            field_schema = properties.get(key, {})
            expected_type = field_schema.get("type")
            if expected_type and not self._is_type_valid(expected_type, value):
                actual_type = type(value).__name__
                raise InputValidationError(
                    f"Input validation failed: field '{key}' expected '{expected_type}' but got '{actual_type}'."
                )

            allowed_values = field_schema.get("enum")
            if allowed_values is not None and value not in allowed_values:
                raise InputValidationError(
                    f"Input validation failed: field '{key}' must be one of {allowed_values}."
                )

            if expected_type == "string":
                min_length = field_schema.get("minLength")
                max_length = field_schema.get("maxLength")
                if min_length is not None and len(value) < min_length:
                    raise InputValidationError(
                        f"Input validation failed: field '{key}' length must be >= {min_length}."
                    )
                if max_length is not None and len(value) > max_length:
                    raise InputValidationError(
                        f"Input validation failed: field '{key}' length must be <= {max_length}."
                    )

            if expected_type in ("integer", "number"):
                minimum = field_schema.get("minimum")
                maximum = field_schema.get("maximum")
                if minimum is not None and value < minimum:
                    raise InputValidationError(
                        f"Input validation failed: field '{key}' must be >= {minimum}."
                    )
                if maximum is not None and value > maximum:
                    raise InputValidationError(
                        f"Input validation failed: field '{key}' must be <= {maximum}."
                    )

            if expected_type == "array":
                min_items = field_schema.get("minItems")
                max_items = field_schema.get("maxItems")
                if min_items is not None and len(value) < min_items:
                    raise InputValidationError(
                        f"Input validation failed: field '{key}' must contain at least {min_items} items."
                    )
                if max_items is not None and len(value) > max_items:
                    raise InputValidationError(
                        f"Input validation failed: field '{key}' must contain at most {max_items} items."
                    )

    def get_hashed_manifest(self) -> Dict[str, str]:
        """Returns a lightweight mapping of original names to their hashed IDs."""
        return self._sorted_by_tool_name(dict(self._hashes))
        
    def get_full_schemas(self) -> Dict[str, dict]:
        """Returns the heavy JSON schemas (only used during initial handshake)."""
        return self._sorted_by_tool_name(deepcopy(self._schemas))

    def get_agent_manifest(self) -> Dict[str, dict]:
        """
        Returns the architect-facing tool manifest:
        hashed tool IDs mapped to JSON-schema parameters only.
        """
        hashed_manifest = self.get_hashed_manifest()
        schemas = self.get_full_schemas()
        return {hashed_manifest[name]: schemas[name]["parameters"] for name in sorted(hashed_manifest)}

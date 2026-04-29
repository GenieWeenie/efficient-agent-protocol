import unittest

from eap.environment import (
    InputValidationError,
    PluginManifestError,
    ToolRegistry,
)


def dummy_tool(value: str) -> str:
    return value


SCHEMA = {
    "name": "dummy_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


class ToolRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register("dummy_tool", dummy_tool, SCHEMA)

    def test_get_tool_by_name_and_hash(self) -> None:
        hashed = self.registry.get_hashed_manifest()["dummy_tool"]
        self.assertIs(self.registry.get_tool("dummy_tool"), dummy_tool)
        self.assertIs(self.registry.get_tool(hashed), dummy_tool)

    def test_get_schema_by_hash(self) -> None:
        hashed = self.registry.get_hashed_manifest()["dummy_tool"]
        schema = self.registry.get_schema(hashed)
        self.assertEqual(schema["name"], "dummy_tool")

    def test_validation_rejects_invalid_type(self) -> None:
        with self.assertRaises(InputValidationError):
            self.registry.validate_arguments("dummy_tool", {"value": 123})

    def test_unknown_tool_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.get_tool("missing_tool")

    def test_type_helper_branches(self) -> None:
        self.assertTrue(ToolRegistry._is_type_valid("string", "x"))
        self.assertTrue(ToolRegistry._is_type_valid("boolean", True))
        self.assertTrue(ToolRegistry._is_type_valid("integer", 1))
        self.assertTrue(ToolRegistry._is_type_valid("number", 1.5))
        self.assertTrue(ToolRegistry._is_type_valid("object", {}))
        self.assertTrue(ToolRegistry._is_type_valid("array", []))
        self.assertFalse(ToolRegistry._is_type_valid("integer", True))

    def test_register_plugin_manifest_registers_tools(self) -> None:
        plugin_manifest = {
            "plugin_name": "plugin_a",
            "tools": [
                {
                    "name": "plugin_echo",
                    "function": dummy_tool,
                    "schema": {
                        "name": "plugin_echo",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
        }
        registered = self.registry.register_plugin_manifest(plugin_manifest, source="unit-test")
        self.assertEqual(registered, ["plugin_echo"])
        self.assertIn("plugin_echo", self.registry.get_hashed_manifest())

    def test_register_plugin_manifest_rejects_invalid_manifest(self) -> None:
        with self.assertRaises(PluginManifestError):
            self.registry.register_plugin_manifest({"plugin_name": "", "tools": []}, source="unit-test")

    # ------------------------------------------------------------------
    # R14: full JSON Schema validation when jsonschema is available.
    # The hand-rolled validator silently accepted ``pattern`` mismatches and
    # nested objects; the new path delegates to Draft 2020-12.
    # ------------------------------------------------------------------
    def test_validation_enforces_string_pattern(self) -> None:
        registry = ToolRegistry()
        registry.register(
            "patterned_tool",
            dummy_tool,
            {
                "name": "patterned_tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "pattern": r"^[A-Z]{3}-\d+$"},
                    },
                    "required": ["code"],
                },
            },
        )
        # Valid pattern passes.
        registry.validate_arguments("patterned_tool", {"code": "ABC-123"})
        # Invalid pattern is rejected.
        with self.assertRaises(InputValidationError) as cm:
            registry.validate_arguments("patterned_tool", {"code": "abc-123"})
        self.assertIn("patterned_tool", str(cm.exception))

    def test_validation_enforces_nested_properties(self) -> None:
        registry = ToolRegistry()
        registry.register(
            "nested_tool",
            dummy_tool,
            {
                "name": "nested_tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user": {
                            "type": "object",
                            "properties": {
                                "age": {"type": "integer", "minimum": 0},
                            },
                            "required": ["age"],
                        },
                    },
                    "required": ["user"],
                },
            },
        )
        registry.validate_arguments("nested_tool", {"user": {"age": 30}})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("nested_tool", {"user": {"age": "not-a-number"}})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("nested_tool", {"user": {}})

    def test_validation_supports_oneof(self) -> None:
        registry = ToolRegistry()
        registry.register(
            "oneof_tool",
            dummy_tool,
            {
                "name": "oneof_tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ident": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "integer"},
                            ],
                        },
                    },
                    "required": ["ident"],
                },
            },
        )
        registry.validate_arguments("oneof_tool", {"ident": "abc"})
        registry.validate_arguments("oneof_tool", {"ident": 42})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("oneof_tool", {"ident": [1, 2, 3]})

    # ------------------------------------------------------------------
    # R14 fallback path (no jsonschema): mirror the legacy hand-rolled
    # validator so coverage remains complete and so that ``ToolRegistry``
    # still works in stripped-down deployments without the optional
    # ``jsonschema`` dependency.
    # ------------------------------------------------------------------
    def _registry_without_jsonschema(self, schema, name="legacy_tool"):
        registry = ToolRegistry()
        registry.register(name, dummy_tool, schema)
        # Force the fallback path by clearing the cached compiled validator.
        registry._validators.pop(name, None)
        return registry

    def test_legacy_validator_enforces_required_fields(self) -> None:
        schema = dict(SCHEMA)
        schema["name"] = "legacy_tool"
        registry = self._registry_without_jsonschema(schema)
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("legacy_tool", {})

    def test_legacy_validator_enforces_type_check(self) -> None:
        schema = dict(SCHEMA)
        schema["name"] = "legacy_tool"
        registry = self._registry_without_jsonschema(schema)
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("legacy_tool", {"value": 123})

    def test_legacy_validator_enforces_string_length_bounds(self) -> None:
        schema = {
            "name": "len_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "minLength": 2, "maxLength": 4},
                },
                "required": ["value"],
            },
        }
        registry = self._registry_without_jsonschema(schema, name="len_tool")
        registry.validate_arguments("len_tool", {"value": "abc"})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("len_tool", {"value": "a"})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("len_tool", {"value": "abcde"})

    def test_legacy_validator_enforces_numeric_bounds_and_arrays(self) -> None:
        schema = {
            "name": "n_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "minimum": 0, "maximum": 5},
                    "tags": {"type": "array", "minItems": 1, "maxItems": 3},
                },
                "required": ["n", "tags"],
            },
        }
        registry = self._registry_without_jsonschema(schema, name="n_tool")
        registry.validate_arguments("n_tool", {"n": 3, "tags": ["a"]})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("n_tool", {"n": -1, "tags": ["a"]})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("n_tool", {"n": 9, "tags": ["a"]})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("n_tool", {"n": 1, "tags": []})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments(
                "n_tool", {"n": 1, "tags": ["a", "b", "c", "d"]}
            )

    def test_legacy_validator_enforces_enum_and_additional_properties(self) -> None:
        schema = {
            "name": "e_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "color": {"type": "string", "enum": ["red", "blue"]},
                },
                "required": ["color"],
                "additionalProperties": False,
            },
        }
        registry = self._registry_without_jsonschema(schema, name="e_tool")
        registry.validate_arguments("e_tool", {"color": "red"})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("e_tool", {"color": "purple"})
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("e_tool", {"color": "red", "extra": 1})

    def test_legacy_validator_rejects_non_object_arguments(self) -> None:
        schema = dict(SCHEMA)
        schema["name"] = "legacy_tool"
        registry = self._registry_without_jsonschema(schema)
        with self.assertRaises(InputValidationError):
            registry.validate_arguments("legacy_tool", "not-a-dict")

    # ------------------------------------------------------------------
    # R17: tool name hash is sha256-derived (no md5 anywhere).
    # ------------------------------------------------------------------
    def test_tool_name_hash_uses_sha256_not_md5(self) -> None:
        import hashlib
        import json as _json

        schema_str = _json.dumps(SCHEMA, sort_keys=True)
        expected_sha = hashlib.sha256(schema_str.encode()).hexdigest()[:8]
        forbidden_md5 = hashlib.md5(schema_str.encode()).hexdigest()[:8]

        hashed = self.registry.get_hashed_manifest()["dummy_tool"]
        suffix = hashed.split("dummy_tool_", 1)[1]
        self.assertEqual(suffix, expected_sha)
        # The previous md5-derived hash must not be produced.
        if expected_sha != forbidden_md5:
            self.assertNotEqual(suffix, forbidden_md5)


if __name__ == "__main__":
    unittest.main()

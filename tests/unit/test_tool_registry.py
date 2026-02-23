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


if __name__ == "__main__":
    unittest.main()

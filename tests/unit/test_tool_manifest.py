import unittest

from eap.environment import ToolRegistry


def tool_a(value: str) -> str:
    return value


def tool_b(count: int) -> str:
    return str(count)


SCHEMA_A = {
    "name": "tool_a",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    },
}

SCHEMA_B = {
    "name": "tool_b",
    "parameters": {
        "type": "object",
        "properties": {"count": {"type": "integer", "minimum": 1}},
        "required": ["count"],
        "additionalProperties": False,
    },
}


class ToolManifestContractTest(unittest.TestCase):
    def test_hashed_manifest_is_stable_across_registration_order(self) -> None:
        first = ToolRegistry()
        first.register("tool_a", tool_a, SCHEMA_A)
        first.register("tool_b", tool_b, SCHEMA_B)

        second = ToolRegistry()
        second.register("tool_b", tool_b, SCHEMA_B)
        second.register("tool_a", tool_a, SCHEMA_A)

        self.assertEqual(first.get_hashed_manifest(), second.get_hashed_manifest())

    def test_agent_manifest_maps_hash_to_parameters(self) -> None:
        registry = ToolRegistry()
        registry.register("tool_a", tool_a, SCHEMA_A)

        hashed_name = registry.get_hashed_manifest()["tool_a"]
        manifest = registry.get_agent_manifest()

        self.assertIn(hashed_name, manifest)
        self.assertEqual(manifest[hashed_name], SCHEMA_A["parameters"])

    def test_schema_hash_changes_when_schema_changes(self) -> None:
        base_registry = ToolRegistry()
        base_registry.register("tool_a", tool_a, SCHEMA_A)
        base_hash = base_registry.get_hashed_manifest()["tool_a"]

        modified_schema = {
            "name": "tool_a",
            "parameters": {
                "type": "object",
                "properties": {"value": {"type": "string", "minLength": 1}},
                "required": ["value"],
                "additionalProperties": False,
            },
        }
        changed_registry = ToolRegistry()
        changed_registry.register("tool_a", tool_a, modified_schema)
        changed_hash = changed_registry.get_hashed_manifest()["tool_a"]

        self.assertNotEqual(base_hash, changed_hash)

    def test_full_schema_snapshot_is_immutable_copy(self) -> None:
        registry = ToolRegistry()
        registry.register("tool_a", tool_a, SCHEMA_A)
        snapshot = registry.get_full_schemas()
        snapshot["tool_a"]["parameters"]["properties"]["value"]["type"] = "integer"

        latest = registry.get_full_schemas()
        self.assertEqual(latest["tool_a"]["parameters"]["properties"]["value"]["type"], "string")


if __name__ == "__main__":
    unittest.main()

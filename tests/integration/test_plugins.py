import asyncio
import os
import pathlib
import sys
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, PluginLoadError, ToolRegistry
from eap.environment.plugin_loader import load_plugins_into_registry
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SAMPLE_PLUGIN_ROOT = PROJECT_ROOT / "examples" / "plugins" / "sample_plugin"


class _FakeEntryPoint:
    def __init__(self, name: str, loader, group: str = "eap.tool_plugins"):
        self.name = name
        self.group = group
        self._loader = loader

    def load(self):
        if isinstance(self._loader, Exception):
            raise self._loader
        return self._loader


class PluginIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(SAMPLE_PLUGIN_ROOT))

    @classmethod
    def tearDownClass(cls) -> None:
        plugin_path = str(SAMPLE_PLUGIN_ROOT)
        if plugin_path in sys.path:
            sys.path.remove(plugin_path)

    def _build_executor(self, registry: ToolRegistry) -> AsyncLocalExecutor:
        fd, db_path = tempfile.mkstemp(prefix="eap-plugin-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))
        state_manager = StateManager(db_path=db_path)
        return AsyncLocalExecutor(state_manager, registry)

    def test_sample_plugin_loads_and_executes(self) -> None:
        import sample_plugin

        registry = ToolRegistry()
        entry_points = lambda: [_FakeEntryPoint("sample_plugin", sample_plugin.get_plugin_manifest)]
        report = load_plugins_into_registry(registry, entry_points_fn=entry_points)

        self.assertEqual(report["failed_plugins"], [])
        self.assertIn("sample_plugin", report["loaded_plugins"])
        self.assertIn("reverse_text", report["loaded_tools"])

        executor = self._build_executor(registry)
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="reverse_1",
                    tool_name="reverse_text",
                    arguments={"text": "plugins"},
                )
            ]
        )
        result = asyncio.run(executor.execute_macro(macro))
        payload = executor.state_manager.retrieve(result["pointer_id"])
        self.assertEqual(payload, "snigulp")

    def test_non_strict_plugin_load_captures_failures(self) -> None:
        registry = ToolRegistry()
        entry_points = lambda: [_FakeEntryPoint("broken_plugin", RuntimeError("boom"))]
        report = load_plugins_into_registry(registry, entry_points_fn=entry_points, strict=False)
        self.assertEqual(report["loaded_plugins"], [])
        self.assertEqual(len(report["failed_plugins"]), 1)
        self.assertEqual(report["failed_plugins"][0]["entry_point"], "broken_plugin")

    def test_strict_plugin_load_raises(self) -> None:
        registry = ToolRegistry()
        entry_points = lambda: [_FakeEntryPoint("broken_plugin", RuntimeError("boom"))]
        with self.assertRaises(PluginLoadError):
            load_plugins_into_registry(registry, entry_points_fn=entry_points, strict=True)


if __name__ == "__main__":
    unittest.main()

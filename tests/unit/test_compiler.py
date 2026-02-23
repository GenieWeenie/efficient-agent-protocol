import unittest

from eap.agent import MacroCompiler, WorkflowGraphCompiler


class CompilerTest(unittest.TestCase):
    def test_compile_extracts_json_from_text(self) -> None:
        raw = "Here you go:\n```json\n{\"steps\": []}\n```"
        macro = MacroCompiler.compile(raw)
        self.assertEqual(len(macro.steps), 0)

    def test_compile_auto_heals_tool_key(self) -> None:
        raw = {
            "steps": [
                {
                    "tool": "read_local_file",
                    "arguments": {"file_path": "/tmp/a.txt"},
                    "step_id": "s1",
                }
            ]
        }
        macro = MacroCompiler.compile(raw)
        self.assertEqual(macro.steps[0].tool_name, "read_local_file")

    def test_compile_adds_missing_step_id(self) -> None:
        raw = {"steps": [{"tool_name": "read_local_file", "arguments": {"file_path": "/tmp/a.txt"}}]}
        macro = MacroCompiler.compile(raw)
        self.assertTrue(macro.steps[0].step_id.startswith("auto_step_"))

    def test_workflow_graph_compiler_validates_payload(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowGraphCompiler.compile_graph({"workflow_id": "wf_x", "nodes": [], "edges": []})


if __name__ == "__main__":
    unittest.main()

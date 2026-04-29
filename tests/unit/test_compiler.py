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

    def test_compile_step_id_is_deterministic_and_content_addressed(self) -> None:
        """The synthesized step_id must be the same across calls and processes.

        Python's built-in ``hash()`` is salted per-process which made the
        previous ``hash(str(step)) % 1000`` recipe non-deterministic. The
        compiler now uses a SHA-256 content hash, so identical step JSON
        always produces the same id and replays/diffs stay stable.
        """
        step = {"tool_name": "read_local_file", "arguments": {"file_path": "/tmp/a.txt"}}
        first = MacroCompiler.compile({"steps": [dict(step)]}).steps[0].step_id
        second = MacroCompiler.compile({"steps": [dict(step)]}).steps[0].step_id
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("auto_step_"))
        # Suffix is the truncated hex digest — must be stable hex chars.
        suffix = first.split("auto_step_", 1)[1]
        self.assertEqual(len(suffix), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in suffix), suffix)

    def test_compile_step_id_changes_when_step_content_changes(self) -> None:
        a = {"tool_name": "read_local_file", "arguments": {"file_path": "/tmp/a.txt"}}
        b = {"tool_name": "read_local_file", "arguments": {"file_path": "/tmp/b.txt"}}
        id_a = MacroCompiler.compile({"steps": [a]}).steps[0].step_id
        id_b = MacroCompiler.compile({"steps": [b]}).steps[0].step_id
        self.assertNotEqual(id_a, id_b)

    def test_workflow_graph_compiler_validates_payload(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowGraphCompiler.compile_graph({"workflow_id": "wf_x", "nodes": [], "edges": []})

    def test_compile_skips_non_json_brace_prefix(self) -> None:
        raw = "template {placeholder}\n{\"steps\": []}"
        macro = MacroCompiler.compile(raw)
        self.assertEqual(len(macro.steps), 0)

    def test_workflow_graph_compiler_extracts_json_from_noisy_text(self) -> None:
        raw = (
            "noise before {not-json}\n"
            '{"workflow_id":"wf_demo","nodes":[{"node_id":"n1","step":{"step_id":"step_1","tool_name":"read_local_file","arguments":{"file_path":"/tmp/a"}}}],"edges":[]}'
        )
        graph = WorkflowGraphCompiler.compile_graph(raw)
        self.assertEqual(graph.workflow_id, "wf_demo")


if __name__ == "__main__":
    unittest.main()

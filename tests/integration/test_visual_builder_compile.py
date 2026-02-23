import json
import unittest

from eap.agent import WorkflowGraphCompiler


class VisualBuilderCompilerIntegrationTest(unittest.TestCase):
    def _graph_payload(self) -> dict:
        return {
            "workflow_id": "wf_visual",
            "nodes": [
                {
                    "node_id": "node_1",
                    "step": {"step_id": "step_1", "tool_name": "tool_a", "arguments": {}},
                    "position_x": 10,
                    "position_y": 20,
                },
                {
                    "node_id": "node_2",
                    "step": {
                        "step_id": "step_2",
                        "tool_name": "tool_b",
                        "arguments": {},
                        "branching": {
                            "condition": "1 == 1",
                            "true_target_step_ids": ["step_3"],
                            "false_target_step_ids": [],
                            "fallback_target_step_ids": [],
                            "allow_early_exit": False,
                        },
                    },
                },
                {
                    "node_id": "node_3",
                    "step": {"step_id": "step_3", "tool_name": "tool_c", "arguments": {}},
                },
            ],
            "edges": [
                {
                    "source_node_id": "node_1",
                    "target_node_id": "node_2",
                    "kind": "dependency",
                },
                {
                    "source_node_id": "node_2",
                    "target_node_id": "node_3",
                    "kind": "dependency",
                },
                {
                    "source_node_id": "node_2",
                    "target_node_id": "node_3",
                    "kind": "branch_true",
                },
            ],
        }

    def test_compile_visual_graph_dict_to_macro(self) -> None:
        macro = WorkflowGraphCompiler.compile_to_macro(
            self._graph_payload(),
            return_final_state_only=False,
            retry_policy={"max_attempts": 2, "initial_delay_seconds": 0.1, "backoff_multiplier": 2.0},
        )
        self.assertFalse(macro.return_final_state_only)
        self.assertEqual([step.step_id for step in macro.steps], ["step_1", "step_2", "step_3"])
        self.assertEqual(macro.steps[1].branching.true_target_step_ids, ["step_3"])
        self.assertEqual(macro.retry_policy.max_attempts, 2)

    def test_compile_visual_graph_from_json_text(self) -> None:
        payload = self._graph_payload()
        raw = f"Graph payload:\n```json\n{json.dumps(payload)}\n```"
        macro = WorkflowGraphCompiler.compile_to_macro(raw)
        self.assertEqual(len(macro.steps), 3)

    def test_compile_rejects_invalid_graph_cycle(self) -> None:
        payload = self._graph_payload()
        payload["edges"].append(
            {"source_node_id": "node_3", "target_node_id": "node_1", "kind": "dependency"}
        )
        with self.assertRaises(ValueError):
            WorkflowGraphCompiler.compile_to_macro(payload)


if __name__ == "__main__":
    unittest.main()

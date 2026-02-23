import unittest

from pydantic import ValidationError

from eap.protocol import BatchedMacroRequest, ToolCall


class BranchingSchemaTest(unittest.TestCase):
    def test_valid_branching_schema(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="analyze",
                    tool_name="tool_a",
                    arguments={},
                    branching={
                        "condition": "$step:analyze.metadata.row_count > 1000",
                        "true_target_step_ids": ["heavy_path"],
                        "false_target_step_ids": ["light_path"],
                    },
                ),
                ToolCall(step_id="heavy_path", tool_name="tool_b", arguments={}),
                ToolCall(step_id="light_path", tool_name="tool_c", arguments={}),
            ]
        )
        self.assertEqual(macro.steps[0].branching.true_target_step_ids, ["heavy_path"])

    def test_branch_target_must_exist(self) -> None:
        with self.assertRaises(ValidationError):
            BatchedMacroRequest(
                steps=[
                    ToolCall(
                        step_id="analyze",
                        tool_name="tool_a",
                        arguments={},
                        branching={
                            "condition": "$step:analyze.metadata.row_count > 1000",
                            "true_target_step_ids": ["missing_step"],
                        },
                    ),
                ]
            )

    def test_branch_target_cannot_self_reference(self) -> None:
        with self.assertRaises(ValidationError):
            BatchedMacroRequest(
                steps=[
                    ToolCall(
                        step_id="analyze",
                        tool_name="tool_a",
                        arguments={},
                        branching={
                            "condition": "1 == 1",
                            "true_target_step_ids": ["analyze"],
                        },
                    ),
                ]
            )

    def test_branch_condition_cannot_be_empty(self) -> None:
        with self.assertRaises(ValidationError):
            ToolCall(
                step_id="analyze",
                tool_name="tool_a",
                arguments={},
                branching={
                    "condition": "   ",
                    "true_target_step_ids": ["next_step"],
                },
            )

    def test_branch_requires_target_or_early_exit(self) -> None:
        with self.assertRaises(ValidationError):
            ToolCall(
                step_id="analyze",
                tool_name="tool_a",
                arguments={},
                branching={
                    "condition": "1 == 1",
                },
            )

    def test_branch_allows_early_exit_without_targets(self) -> None:
        step = ToolCall(
            step_id="analyze",
            tool_name="tool_a",
            arguments={},
            branching={
                "condition": "$step:analyze.metadata.done == true",
                "allow_early_exit": True,
            },
        )
        self.assertTrue(step.branching.allow_early_exit)


if __name__ == "__main__":
    unittest.main()

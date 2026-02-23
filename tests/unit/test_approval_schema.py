import unittest

from pydantic import ValidationError

from eap.protocol import BatchedMacroRequest, ToolCall


class ApprovalSchemaTests(unittest.TestCase):
    def test_valid_approval_checkpoint_and_decision(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="step_1",
                    tool_name="tool_a",
                    arguments={},
                    approval={"required": True, "prompt": "Require reviewer approval."},
                )
            ],
            approvals={"step_1": {"decision": "approve"}},
        )
        self.assertEqual(macro.approvals["step_1"].decision.value, "approve")

    def test_reject_decision_requires_reason(self) -> None:
        with self.assertRaises(ValidationError):
            BatchedMacroRequest(
                steps=[
                    ToolCall(
                        step_id="step_1",
                        tool_name="tool_a",
                        arguments={},
                        approval={"required": True},
                    )
                ],
                approvals={"step_1": {"decision": "reject"}},
            )

    def test_approval_decision_requires_valid_step_id(self) -> None:
        with self.assertRaises(ValidationError):
            BatchedMacroRequest(
                steps=[ToolCall(step_id="step_1", tool_name="tool_a", arguments={})],
                approvals={"step_2": {"decision": "approve"}},
            )

    def test_approval_decision_requires_approval_checkpoint(self) -> None:
        with self.assertRaises(ValidationError):
            BatchedMacroRequest(
                steps=[ToolCall(step_id="step_1", tool_name="tool_a", arguments={})],
                approvals={"step_1": {"decision": "approve"}},
            )


if __name__ == "__main__":
    unittest.main()

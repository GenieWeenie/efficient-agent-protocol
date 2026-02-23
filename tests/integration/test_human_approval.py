import asyncio
import os
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


class TrackingTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str) -> str:
        self.calls += 1
        return f"ok:{value}"


TOOL_SCHEMA = {
    "name": "approval_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


class HumanApprovalIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-approval-", suffix=".db")
        os.close(fd)
        self.state_manager = StateManager(db_path=self.db_path)
        self.registry = ToolRegistry()
        self.tool = TrackingTool()
        self.registry.register("approval_tool", self.tool, TOOL_SCHEMA)
        self.executor = AsyncLocalExecutor(self.state_manager, self.registry)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_step_pauses_when_approval_is_missing(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="step_1",
                    tool_name="approval_tool",
                    arguments={"value": "x"},
                    approval={"required": True, "prompt": "Need manual review."},
                )
            ]
        )

        result = asyncio.run(self.executor.execute_macro(macro))
        run_id = result["metadata"]["execution_run_id"]

        self.assertEqual(self.tool.calls, 0)
        self.assertEqual(result["metadata"]["approval_metrics"]["paused_steps"], 1)
        events = self.state_manager.list_trace_events(run_id)
        self.assertEqual(
            [event.event_type.value for event in events],
            ["queued", "approval_required"],
        )
        summary = self.state_manager.get_execution_summary(run_id)
        self.assertEqual(summary["succeeded_steps"], 0)
        self.assertEqual(summary["failed_steps"], 1)

    def test_step_executes_after_explicit_approval(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="step_1",
                    tool_name="approval_tool",
                    arguments={"value": "x"},
                    approval={"required": True},
                )
            ],
            approvals={"step_1": {"decision": "approve"}},
        )

        result = asyncio.run(self.executor.execute_macro(macro))
        run_id = result["metadata"]["execution_run_id"]

        self.assertEqual(self.tool.calls, 1)
        self.assertEqual(result["metadata"]["approval_metrics"]["approved_steps"], 1)
        events = self.state_manager.list_trace_events(run_id)
        self.assertEqual(
            [event.event_type.value for event in events],
            ["queued", "approval_required", "approved", "started", "completed"],
        )
        summary = self.state_manager.get_execution_summary(run_id)
        self.assertEqual(summary["succeeded_steps"], 1)
        self.assertEqual(summary["failed_steps"], 0)

    def test_step_rejection_captures_reason_in_trace(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="step_1",
                    tool_name="approval_tool",
                    arguments={"value": "x"},
                    approval={"required": True},
                )
            ],
            approvals={"step_1": {"decision": "reject", "reason": "Unsafe operation."}},
        )

        result = asyncio.run(self.executor.execute_macro(macro))
        run_id = result["metadata"]["execution_run_id"]

        self.assertEqual(self.tool.calls, 0)
        self.assertEqual(result["metadata"]["approval_metrics"]["rejected_steps"], 1)
        events = self.state_manager.list_trace_events(run_id)
        self.assertEqual(
            [event.event_type.value for event in events],
            ["queued", "approval_required", "rejected"],
        )
        rejected = events[-1]
        self.assertIsNotNone(rejected.error)
        self.assertEqual(rejected.error.error_type, "approval_rejected")
        self.assertEqual(rejected.error.message, "Unsafe operation.")
        summary = self.state_manager.get_execution_summary(run_id)
        self.assertEqual(summary["succeeded_steps"], 0)
        self.assertEqual(summary["failed_steps"], 1)


if __name__ == "__main__":
    unittest.main()

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, ExecutionTraceEventType, StateManager, ToolCall


class CountingTool:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.calls = 0

    def __call__(self, value: str = "") -> str:
        self.calls += 1
        return f"{self.prefix}:{value}"


TOOL_SCHEMA = {
    "name": "step_one",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": [],
    },
}


class ResumeReplayIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-resume-", suffix=".db")
        os.close(fd)
        self.state_manager = StateManager(db_path=self.db_path)
        self.registry = ToolRegistry()
        self.step_one_tool = CountingTool("one")
        self.step_two_tool = CountingTool("two")
        step_one_schema = dict(TOOL_SCHEMA)
        step_one_schema["name"] = "step_one"
        step_two_schema = dict(TOOL_SCHEMA)
        step_two_schema["name"] = "step_two"
        self.registry.register("step_one", self.step_one_tool, step_one_schema)
        self.registry.register("step_two", self.step_two_tool, step_two_schema)
        self.executor = AsyncLocalExecutor(self.state_manager, self.registry)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_resume_replays_checkpointed_steps_and_executes_pending_steps(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="step_1", tool_name="step_one", arguments={"value": "seed"}),
                ToolCall(step_id="step_2", tool_name="step_two", arguments={"value": "$step:step_1"}),
            ]
        )
        checkpoint_pointer = self.state_manager.store_and_point(
            raw_data="one:seed",
            summary="Recovered step_1 output",
            metadata={"status": "ok"},
        )
        run_id = "run_resume_001"
        self.state_manager.upsert_run_checkpoint(
            run_id=run_id,
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            status="active",
            macro_payload=macro.model_dump(mode="json"),
            step_status={"step_1": {"status": "ok", "pointer_id": checkpoint_pointer["pointer_id"]}},
            branch_decisions={},
        )

        result = asyncio.run(self.executor.resume_run(run_id))
        self.assertEqual(result["metadata"]["execution_run_id"], run_id)
        self.assertTrue(result["metadata"]["resumed_from_checkpoint"])
        self.assertEqual(result["metadata"]["replayed_steps"], ["step_1"])
        self.assertEqual(self.step_one_tool.calls, 0)
        self.assertEqual(self.step_two_tool.calls, 1)

        events = self.state_manager.list_trace_events(run_id)
        step_one_event_types = [e.event_type for e in events if e.step_id == "step_1"]
        self.assertEqual(step_one_event_types, [ExecutionTraceEventType.REPLAYED])

        summary = self.state_manager.get_execution_summary(run_id)
        self.assertEqual(summary["succeeded_steps"], 2)
        self.assertEqual(summary["failed_steps"], 0)

    def test_resume_advances_awaiting_approval_runs(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="step_1",
                    tool_name="step_one",
                    arguments={"value": "approve-me"},
                    approval={"required": True},
                )
            ]
        )
        initial = asyncio.run(self.executor.execute_macro(macro))
        run_id = initial["metadata"]["execution_run_id"]
        checkpoint = self.state_manager.get_run_checkpoint(run_id)
        self.assertEqual(checkpoint["status"], "awaiting_approval")

        resumed = asyncio.run(
            self.executor.resume_run(
                run_id,
                approvals={"step_1": {"decision": "approve"}},
            )
        )
        self.assertEqual(resumed["metadata"]["execution_run_id"], run_id)
        self.assertEqual(resumed["metadata"]["checkpoint_status"], "completed")
        self.assertEqual(self.step_one_tool.calls, 1)

    def test_resume_missing_checkpoint_raises(self) -> None:
        with self.assertRaises(KeyError):
            asyncio.run(self.executor.resume_run("run_missing"))


if __name__ == "__main__":
    unittest.main()

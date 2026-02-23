import asyncio
import os
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


class FlakyTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("first call fails")
        return value


def always_fail(value: str) -> str:
    raise RuntimeError("always failing")


TOOL_SCHEMA = {
    "name": "trace_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


class ExecutionTraceIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-trace-", suffix=".db")
        os.close(fd)
        self.state_manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_retry_and_completion_events_are_persisted(self) -> None:
        registry = ToolRegistry()
        registry.register("trace_tool", FlakyTool(), TOOL_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="trace_tool", arguments={"value": "ok"})],
            retry_policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )

        result = asyncio.run(executor.execute_macro(macro))
        run_id = result["metadata"]["execution_run_id"]

        events = self.state_manager.list_trace_events(run_id)
        event_types = [event.event_type.value for event in events]
        self.assertEqual(event_types, ["queued", "started", "retried", "started", "completed"])

        summary = self.state_manager.get_execution_summary(run_id)
        self.assertEqual(summary["total_steps"], 1)
        self.assertEqual(summary["succeeded_steps"], 1)
        self.assertEqual(summary["failed_steps"], 0)
        self.assertEqual(summary["final_pointer_id"], result["pointer_id"])

    def test_failed_event_and_summary_are_persisted(self) -> None:
        registry = ToolRegistry()
        registry.register("trace_tool", always_fail, TOOL_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="trace_tool", arguments={"value": "x"})],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )

        result = asyncio.run(executor.execute_macro(macro))
        run_id = result["metadata"]["execution_run_id"]

        events = self.state_manager.list_trace_events(run_id)
        event_types = [event.event_type.value for event in events]
        self.assertEqual(event_types, ["queued", "started", "failed"])

        summary = self.state_manager.get_execution_summary(run_id)
        self.assertEqual(summary["succeeded_steps"], 0)
        self.assertEqual(summary["failed_steps"], 1)
        self.assertEqual(summary["final_pointer_id"], result["pointer_id"])


if __name__ == "__main__":
    unittest.main()

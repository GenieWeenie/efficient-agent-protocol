import asyncio
import os
import tempfile
import time
import unittest

from pydantic import ValidationError

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, ExecutionLimits, StateManager, ToolCall


def echo_tool(x: str) -> str:
    return x


def slow_tool(x: str, delay_seconds: float = 0.2) -> str:
    time.sleep(delay_seconds)
    return x


ECHO_SCHEMA = {
    "name": "echo_tool",
    "parameters": {
        "type": "object",
        "properties": {"x": {"type": "string"}, "delay_seconds": {"type": "number"}},
        "required": ["x"],
    },
}

SLOW_SCHEMA = {
    "name": "slow_tool",
    "parameters": {
        "type": "object",
        "properties": {"x": {"type": "string"}, "delay_seconds": {"type": "number"}},
        "required": ["x"],
    },
}


class ExecutorErrorContractTest(unittest.TestCase):
    def _build_executor(self) -> AsyncLocalExecutor:
        fd, db_path = tempfile.mkstemp(prefix="eap-test-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))
        state_manager = StateManager(db_path=db_path)
        registry = ToolRegistry()
        registry.register("echo_tool", echo_tool, ECHO_SCHEMA)
        registry.register("slow_tool", slow_tool, SLOW_SCHEMA)
        return AsyncLocalExecutor(state_manager, registry)

    def test_validation_error_returns_error_pointer(self) -> None:
        executor = self._build_executor()
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="echo_tool", arguments={})]
        )
        result = asyncio.run(executor.execute_macro(macro))
        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "validation_error")

    def test_dependency_error_returns_error_pointer(self) -> None:
        executor = self._build_executor()
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="echo_tool", arguments={"x": "$missing_step"})]
        )
        result = asyncio.run(executor.execute_macro(macro))
        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "dependency_error")

    def test_direct_dependency_cycle_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            BatchedMacroRequest(
                steps=[ToolCall(step_id="step_1", tool_name="echo_tool", arguments={"x": "$step:step_1"})]
            )
        self.assertIn("macro dependency graph contains a cycle", str(ctx.exception))

    def test_indirect_dependency_cycle_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            BatchedMacroRequest(
                steps=[
                    ToolCall(step_id="step_a", tool_name="echo_tool", arguments={"x": "$step:step_b"}),
                    ToolCall(step_id="step_b", tool_name="echo_tool", arguments={"x": "$step:step_a"}),
                ]
            )
        self.assertIn("macro dependency graph contains a cycle", str(ctx.exception))

    def test_macro_total_timeout_returns_structured_error_pointer(self) -> None:
        executor = self._build_executor()
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="slow", tool_name="slow_tool", arguments={"x": "ok", "delay_seconds": 0.2})],
            execution_limits=ExecutionLimits(max_total_runtime_seconds=0.05),
        )

        result = asyncio.run(executor.execute_macro(macro))

        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "macro_timeout")
        self.assertEqual(result["metadata"]["checkpoint_status"], "completed")
        run_id = result["metadata"]["execution_run_id"]
        events = executor.state_manager.list_trace_events(run_id)
        failed_event = next(event for event in events if event.event_type.value == "failed")
        self.assertEqual(failed_event.error.error_type, "macro_timeout")
        self.assertIn("max_total_runtime_seconds", failed_event.error.message)

    def test_nested_reference_resolution_depth_is_bounded(self) -> None:
        executor = self._build_executor()
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="seed", tool_name="echo_tool", arguments={"x": "ok"}),
                ToolCall(
                    step_id="nested",
                    tool_name="echo_tool",
                    arguments={"x": {"too": {"deep": "$step:seed"}}},
                ),
            ],
            execution_limits=ExecutionLimits(max_reference_resolution_depth=1),
        )

        result = asyncio.run(executor.execute_macro(macro))

        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "validation_error")


if __name__ == "__main__":
    unittest.main()

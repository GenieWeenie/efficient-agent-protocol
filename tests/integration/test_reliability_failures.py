import asyncio
import os
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


class TimeoutThenSuccessTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("operation timed out")
        return value


class AlwaysTimeoutTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str) -> str:
        self.calls += 1
        raise TimeoutError("operation timed out")


def always_fail(value: str) -> str:
    raise RuntimeError("forced upstream failure")


def echo_tool(value: str) -> str:
    return value


TOOL_SCHEMA = {
    "name": "reliability_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}

FAIL_TOOL_SCHEMA = {
    "name": "fail_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}

ECHO_TOOL_SCHEMA = {
    "name": "echo_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


class ReliabilityFailureIntegrationTest(unittest.TestCase):
    def _build_state_manager(self) -> StateManager:
        fd, db_path = tempfile.mkstemp(prefix="eap-reliability-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))
        return StateManager(db_path=db_path)

    def _build_executor(self, state_manager: StateManager, tool_callable, tool_name: str = "reliability_tool"):
        registry = ToolRegistry()
        registry.register(tool_name, tool_callable, TOOL_SCHEMA)
        return AsyncLocalExecutor(state_manager, registry)

    def test_timeout_error_is_retried_when_retryable(self) -> None:
        state_manager = self._build_state_manager()
        flaky_timeout = TimeoutThenSuccessTool()
        executor = self._build_executor(state_manager, flaky_timeout)
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="reliability_tool", arguments={"value": "ok"})],
            retry_policy=RetryPolicy(
                max_attempts=2,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
                retryable_error_types=["TimeoutError"],
            ),
        )

        result = asyncio.run(executor.execute_macro(macro))
        self.assertNotIn("status", result.get("metadata", {}))
        self.assertEqual(flaky_timeout.calls, 2)

        run_id = result["metadata"]["execution_run_id"]
        events = state_manager.list_trace_events(run_id)
        self.assertEqual(
            [event.event_type.value for event in events],
            ["queued", "started", "retried", "started", "completed"],
        )
        retried_event = next(event for event in events if event.event_type.value == "retried")
        self.assertEqual(retried_event.error.error_type, "tool_execution_error")
        self.assertIn("timed out", retried_event.error.message)

    def test_timeout_error_is_not_retried_when_not_retryable(self) -> None:
        state_manager = self._build_state_manager()
        always_timeout = AlwaysTimeoutTool()
        executor = self._build_executor(state_manager, always_timeout)
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="reliability_tool", arguments={"value": "x"})],
            retry_policy=RetryPolicy(
                max_attempts=3,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
                retryable_error_types=["RuntimeError"],
            ),
        )

        result = asyncio.run(executor.execute_macro(macro))
        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "tool_execution_error")
        self.assertEqual(always_timeout.calls, 1)

        run_id = result["metadata"]["execution_run_id"]
        events = state_manager.list_trace_events(run_id)
        self.assertEqual([event.event_type.value for event in events], ["queued", "started", "failed"])
        failed_event = next(event for event in events if event.event_type.value == "failed")
        self.assertEqual(failed_event.attempt, 1)
        self.assertIn("timed out", failed_event.error.message)

    def test_upstream_dependency_failure_propagates_to_downstream_step(self) -> None:
        state_manager = self._build_state_manager()
        registry = ToolRegistry()
        registry.register("fail_tool", always_fail, FAIL_TOOL_SCHEMA)
        registry.register("echo_tool", echo_tool, ECHO_TOOL_SCHEMA)
        executor = AsyncLocalExecutor(state_manager, registry)
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="step_fail", tool_name="fail_tool", arguments={"value": "x"}),
                ToolCall(step_id="step_dep", tool_name="echo_tool", arguments={"value": "$step:step_fail"}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )

        result = asyncio.run(executor.execute_macro(macro))
        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "dependency_error")

        run_id = result["metadata"]["execution_run_id"]
        events = state_manager.list_trace_events(run_id)
        fail_events = [event for event in events if event.step_id == "step_fail"]
        dep_events = [event for event in events if event.step_id == "step_dep"]

        self.assertEqual([event.event_type.value for event in fail_events], ["queued", "started", "failed"])
        self.assertEqual([event.event_type.value for event in dep_events], ["queued", "failed"])
        self.assertEqual(fail_events[-1].error.error_type, "tool_execution_error")
        self.assertEqual(dep_events[-1].error.error_type, "dependency_error")


if __name__ == "__main__":
    unittest.main()

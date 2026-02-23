import asyncio
import os
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


def always_fail(value: str) -> str:
    raise RuntimeError("forced failure")


class FlakyTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str) -> str:
        self.calls += 1
        if self.calls < 2:
            raise RuntimeError("transient failure")
        return value


TOOL_SCHEMA = {
    "name": "retry_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


class ExecutorRetryIntegrationTest(unittest.TestCase):
    def _build_executor(self, tool_callable) -> AsyncLocalExecutor:
        fd, db_path = tempfile.mkstemp(prefix="eap-retry-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))
        state_manager = StateManager(db_path=db_path)
        registry = ToolRegistry()
        registry.register("retry_tool", tool_callable, TOOL_SCHEMA)
        return AsyncLocalExecutor(state_manager, registry)

    def test_success_after_retry(self) -> None:
        flaky = FlakyTool()
        executor = self._build_executor(flaky)
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="retry_tool", arguments={"value": "ok"})],
            retry_policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )
        result = asyncio.run(executor.execute_macro(macro))
        self.assertNotIn("status", result.get("metadata", {}))
        self.assertEqual(flaky.calls, 2)

    def test_max_retries_exceeded(self) -> None:
        executor = self._build_executor(always_fail)
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="step_1", tool_name="retry_tool", arguments={"value": "x"})],
            retry_policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )
        result = asyncio.run(executor.execute_macro(macro))
        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "tool_execution_error")

    def test_dependency_blocked_propagation(self) -> None:
        executor = self._build_executor(always_fail)
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="step_fail", tool_name="retry_tool", arguments={"value": "x"}),
                ToolCall(step_id="step_dep", tool_name="retry_tool", arguments={"value": "$step:step_fail"}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )
        result = asyncio.run(executor.execute_macro(macro))
        self.assertEqual(result["metadata"]["status"], "error")
        self.assertEqual(result["metadata"]["error_type"], "dependency_error")


if __name__ == "__main__":
    unittest.main()

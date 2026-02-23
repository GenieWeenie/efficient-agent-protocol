import asyncio
import os
import tempfile
import threading
import time
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import (
    BatchedMacroRequest,
    ExecutionLimits,
    RetryPolicy,
    StateManager,
    ToolCall,
    ToolExecutionLimit,
)


class _ConcurrencyTrackerTool:
    def __init__(self, sleep_seconds: float = 0.05) -> None:
        self._lock = threading.Lock()
        self._inflight = 0
        self.max_inflight = 0
        self.sleep_seconds = sleep_seconds

    def __call__(self, value: str) -> str:
        with self._lock:
            self._inflight += 1
            if self._inflight > self.max_inflight:
                self.max_inflight = self._inflight
        try:
            time.sleep(self.sleep_seconds)
            return value
        finally:
            with self._lock:
                self._inflight -= 1


TOOL_SCHEMA = {
    "name": "tracked_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    },
}


class ConcurrencyLimitsPerfTest(unittest.TestCase):
    def _build_executor(self, tool_callable) -> AsyncLocalExecutor:
        fd, db_path = tempfile.mkstemp(prefix="eap-limits-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))
        state_manager = StateManager(db_path=db_path)
        registry = ToolRegistry()
        registry.register("tracked_tool", tool_callable, TOOL_SCHEMA)
        return AsyncLocalExecutor(state_manager, registry)

    def test_global_concurrency_limit_caps_parallel_work(self) -> None:
        tracker = _ConcurrencyTrackerTool(sleep_seconds=0.06)
        executor = self._build_executor(tracker)
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id=f"step_{idx}", tool_name="tracked_tool", arguments={"value": str(idx)})
                for idx in range(12)
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
            execution_limits=ExecutionLimits(max_global_concurrency=3),
        )
        result = asyncio.run(executor.execute_macro(macro))
        metrics = result["metadata"]["saturation_metrics"]

        self.assertLessEqual(tracker.max_inflight, 3)
        self.assertLessEqual(metrics["max_inflight_global"], 3)
        self.assertGreater(metrics["global_concurrency_wait_count"], 0)

    def test_rate_limit_generates_saturation_metrics(self) -> None:
        tracker = _ConcurrencyTrackerTool(sleep_seconds=0.01)
        executor = self._build_executor(tracker)
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id=f"step_{idx}", tool_name="tracked_tool", arguments={"value": str(idx)})
                for idx in range(6)
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
            execution_limits=ExecutionLimits(
                max_global_concurrency=6,
                global_requests_per_second=3.0,
                global_burst_capacity=1,
                per_tool={
                    "tracked_tool": ToolExecutionLimit(
                        max_concurrency=2,
                        requests_per_second=20.0,
                        burst_capacity=2,
                    )
                },
            ),
        )
        started = time.perf_counter()
        result = asyncio.run(executor.execute_macro(macro))
        elapsed = time.perf_counter() - started
        metrics = result["metadata"]["saturation_metrics"]

        self.assertGreaterEqual(elapsed, 1.3)
        self.assertGreater(metrics["global_rate_wait_count"], 0)
        self.assertGreater(metrics["global_rate_wait_seconds"], 0.0)
        self.assertGreater(metrics["total_rate_limited_attempts"], 0)
        self.assertLessEqual(metrics["max_inflight_per_tool"]["tracked_tool"], 2)


if __name__ == "__main__":
    unittest.main()

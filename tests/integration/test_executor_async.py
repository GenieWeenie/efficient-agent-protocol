import asyncio
import os
import tempfile
import time
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


def slow_fetch(query: str) -> str:
    time.sleep(0.2)
    return f"DATA_{query}"


def combine_data(data1: str, data2: str) -> str:
    time.sleep(0.1)
    return f"{data1}|{data2}"


FETCH_SCHEMA = {
    "name": "slow_fetch",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

COMBINE_SCHEMA = {
    "name": "combine_data",
    "parameters": {
        "type": "object",
        "properties": {
            "data1": {"type": "string"},
            "data2": {"type": "string"},
        },
        "required": ["data1", "data2"],
    },
}


class ExecutorAsyncIntegrationTest(unittest.TestCase):
    def _build_executor(self) -> AsyncLocalExecutor:
        fd, db_path = tempfile.mkstemp(prefix="eap-async-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))
        state_manager = StateManager(db_path=db_path)
        registry = ToolRegistry()
        registry.register("slow_fetch", slow_fetch, FETCH_SCHEMA)
        registry.register("combine_data", combine_data, COMBINE_SCHEMA)
        return AsyncLocalExecutor(state_manager, registry)

    def test_parallel_execution_reduces_wall_time(self) -> None:
        executor = self._build_executor()
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="a", tool_name="slow_fetch", arguments={"query": "one"}),
                ToolCall(step_id="b", tool_name="slow_fetch", arguments={"query": "two"}),
                ToolCall(step_id="c", tool_name="combine_data", arguments={"data1": "$step:a", "data2": "$step:b"}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )
        started = time.perf_counter()
        result = asyncio.run(executor.execute_macro(macro))
        elapsed = time.perf_counter() - started

        self.assertIn("pointer_id", result)
        self.assertLess(elapsed, 0.55)


if __name__ == "__main__":
    unittest.main()


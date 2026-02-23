import asyncio
import os
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


def fetch_data(query: str) -> str:
    return f"RAW:{query}"


def transform_data(raw_data: str, focus: str) -> str:
    return f"FOCUS:{focus}|{raw_data}"


FETCH_SCHEMA = {
    "name": "fetch_data",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

TRANSFORM_SCHEMA = {
    "name": "transform_data",
    "parameters": {
        "type": "object",
        "properties": {
            "raw_data": {"type": "string"},
            "focus": {"type": "string"},
        },
        "required": ["raw_data", "focus"],
    },
}


class PointerFlowIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-ptr-", suffix=".db")
        os.close(fd)
        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("fetch_data", fetch_data, FETCH_SCHEMA)
        registry.register("transform_data", transform_data, TRANSFORM_SCHEMA)
        self.executor = AsyncLocalExecutor(self.state_manager, registry)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_step_pointer_reference_flow(self) -> None:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="step_fetch", tool_name="fetch_data", arguments={"query": "sales"}),
                ToolCall(
                    step_id="step_transform",
                    tool_name="transform_data",
                    arguments={"raw_data": "$step:step_fetch", "focus": "summary"},
                ),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )
        result = asyncio.run(self.executor.execute_macro(macro))
        payload = self.state_manager.retrieve(result["pointer_id"])
        self.assertIn("FOCUS:summary", payload)
        self.assertIn("RAW:sales", payload)


if __name__ == "__main__":
    unittest.main()


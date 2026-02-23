import asyncio
import os
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


def echo_tool(x: str) -> str:
    return x


ECHO_SCHEMA = {
    "name": "echo_tool",
    "parameters": {
        "type": "object",
        "properties": {"x": {"type": "string"}},
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


if __name__ == "__main__":
    unittest.main()

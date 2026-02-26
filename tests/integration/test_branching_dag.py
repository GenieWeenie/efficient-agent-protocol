import asyncio
import os
import tempfile
import unittest

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


ANALYZE_SCHEMA = {
    "name": "analyze",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
HEAVY_SCHEMA = {
    "name": "heavy_path",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
LIGHT_SCHEMA = {
    "name": "light_path",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
PRIMARY_SCHEMA = {
    "name": "primary_step",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
FALLBACK_SCHEMA = {
    "name": "fallback_step",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


class BranchingDagIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-branch-", suffix=".db")
        os.close(fd)
        self.state_manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _new_executor(self) -> AsyncLocalExecutor:
        return AsyncLocalExecutor(self.state_manager, ToolRegistry())

    def test_true_branch_executes_only_true_targets(self) -> None:
        counters = {"heavy": 0, "light": 0}

        def analyze() -> dict:
            return {"metadata": {"row_count": 1501}}

        def heavy_path() -> str:
            counters["heavy"] += 1
            return "heavy-ok"

        def light_path() -> str:
            counters["light"] += 1
            return "light-ok"

        registry = ToolRegistry()
        registry.register("analyze", analyze, ANALYZE_SCHEMA)
        registry.register("heavy_path", heavy_path, HEAVY_SCHEMA)
        registry.register("light_path", light_path, LIGHT_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="analyze",
                    tool_name="analyze",
                    arguments={},
                    branching={
                        "condition": "$step:analyze.raw_data.metadata.row_count > 1000",
                        "true_target_step_ids": ["heavy"],
                        "false_target_step_ids": ["light"],
                    },
                ),
                ToolCall(step_id="heavy", tool_name="heavy_path", arguments={}),
                ToolCall(step_id="light", tool_name="light_path", arguments={}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )

        asyncio.run(executor.execute_macro(macro))
        self.assertEqual(counters["heavy"], 1)
        self.assertEqual(counters["light"], 0)

    def test_false_branch_executes_only_false_targets(self) -> None:
        counters = {"heavy": 0, "light": 0}

        def analyze() -> dict:
            return {"metadata": {"row_count": 12}}

        def heavy_path() -> str:
            counters["heavy"] += 1
            return "heavy-ok"

        def light_path() -> str:
            counters["light"] += 1
            return "light-ok"

        registry = ToolRegistry()
        registry.register("analyze", analyze, ANALYZE_SCHEMA)
        registry.register("heavy_path", heavy_path, HEAVY_SCHEMA)
        registry.register("light_path", light_path, LIGHT_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="analyze",
                    tool_name="analyze",
                    arguments={},
                    branching={
                        "condition": "$step:analyze.raw_data.metadata.row_count > 1000",
                        "true_target_step_ids": ["heavy"],
                        "false_target_step_ids": ["light"],
                    },
                ),
                ToolCall(step_id="heavy", tool_name="heavy_path", arguments={}),
                ToolCall(step_id="light", tool_name="light_path", arguments={}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )

        asyncio.run(executor.execute_macro(macro))
        self.assertEqual(counters["heavy"], 0)
        self.assertEqual(counters["light"], 1)

    def test_failure_branch_executes_fallback_targets(self) -> None:
        counters = {"fallback": 0}

        def primary_step() -> str:
            raise RuntimeError("primary failed")

        def fallback_step() -> str:
            counters["fallback"] += 1
            return "fallback-ok"

        registry = ToolRegistry()
        registry.register("primary_step", primary_step, PRIMARY_SCHEMA)
        registry.register("fallback_step", fallback_step, FALLBACK_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="primary",
                    tool_name="primary_step",
                    arguments={},
                    branching={
                        "condition": "1 == 1",
                        "fallback_target_step_ids": ["fallback"],
                    },
                ),
                ToolCall(step_id="fallback", tool_name="fallback_step", arguments={}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )

        result = asyncio.run(executor.execute_macro(macro))
        self.assertEqual(counters["fallback"], 1)
        self.assertIn("pointer_id", result)

    def test_unsafe_branch_expression_is_rejected(self) -> None:
        counters = {"heavy": 0, "light": 0}

        def analyze() -> dict:
            return {"metadata": {"row_count": 1501}}

        def heavy_path() -> str:
            counters["heavy"] += 1
            return "heavy-ok"

        def light_path() -> str:
            counters["light"] += 1
            return "light-ok"

        registry = ToolRegistry()
        registry.register("analyze", analyze, ANALYZE_SCHEMA)
        registry.register("heavy_path", heavy_path, HEAVY_SCHEMA)
        registry.register("light_path", light_path, LIGHT_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="analyze",
                    tool_name="analyze",
                    arguments={},
                    branching={
                        "condition": "__import__('os').system('echo pwned') == 0",
                        "true_target_step_ids": ["heavy"],
                        "false_target_step_ids": ["light"],
                    },
                ),
                ToolCall(step_id="heavy", tool_name="heavy_path", arguments={}),
                ToolCall(step_id="light", tool_name="light_path", arguments={}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )

        result = asyncio.run(executor.execute_macro(macro))
        run_id = result["metadata"]["execution_run_id"]
        checkpoint = self.state_manager.get_run_checkpoint(run_id=run_id)
        analyze_pointer = checkpoint["step_status"]["analyze"]["pointer_id"]
        analyze_payload = self.state_manager.retrieve(analyze_pointer)

        self.assertEqual(checkpoint["step_status"]["analyze"]["status"], "error")
        self.assertIn("'error_type': 'validation_error'", analyze_payload)
        self.assertIn("Unsafe branch condition expression", analyze_payload)
        self.assertEqual(counters["heavy"], 0)
        self.assertEqual(counters["light"], 0)


if __name__ == "__main__":
    unittest.main()

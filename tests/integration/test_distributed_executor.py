import os
import tempfile
import unittest

from eap.environment import DistributedCoordinator, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


ECHO_SCHEMA = {
    "name": "echo",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}
APPEND_SCHEMA = {
    "name": "append_suffix",
    "parameters": {
        "type": "object",
        "properties": {"base": {"type": "string"}, "suffix": {"type": "string"}},
        "required": ["base", "suffix"],
    },
}
FLAKY_SCHEMA = {
    "name": "flaky",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


class DistributedExecutorIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-dist-", suffix=".db")
        os.close(fd)
        self.state_manager = StateManager(db_path=self.db_path)
        self.registry = ToolRegistry()

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_worker_loop_executes_dependency_ordered_steps(self) -> None:
        self.registry.register("echo", lambda value: value, ECHO_SCHEMA)
        self.registry.register("append_suffix", lambda base, suffix: f"{base}{suffix}", APPEND_SCHEMA)
        coordinator = DistributedCoordinator(
            state_manager=self.state_manager,
            registry=self.registry,
            db_path=self.db_path,
            lease_ttl_seconds=10,
        )

        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="s1", tool_name="echo", arguments={"value": "hello"}),
                ToolCall(
                    step_id="s2",
                    tool_name="append_suffix",
                    arguments={"base": "$step:s1", "suffix": "-world"},
                ),
            ]
        )
        run_id = coordinator.enqueue_macro(macro)
        coordinator.execute_worker_loop(worker_id="worker-1", max_iterations=40)

        steps = coordinator.list_run_steps(run_id)
        status_by_step = {row["step_id"]: row["status"] for row in steps}
        self.assertEqual(status_by_step["s1"], "completed")
        self.assertEqual(status_by_step["s2"], "completed")

    def test_worker_loop_retries_failed_step_until_success(self) -> None:
        call_counter = {"flaky": 0}

        def flaky() -> str:
            call_counter["flaky"] += 1
            if call_counter["flaky"] == 1:
                raise RuntimeError("temporary failure")
            return "ok"

        self.registry.register("flaky", flaky, FLAKY_SCHEMA)
        coordinator = DistributedCoordinator(
            state_manager=self.state_manager,
            registry=self.registry,
            db_path=self.db_path,
            lease_ttl_seconds=10,
        )
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="s1", tool_name="flaky", arguments={})],
            retry_policy=RetryPolicy(
                max_attempts=2,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
            ),
        )
        run_id = coordinator.enqueue_macro(macro)
        coordinator.execute_worker_loop(worker_id="worker-2", max_iterations=40)

        steps = coordinator.list_run_steps(run_id)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["status"], "completed")
        self.assertEqual(steps[0]["attempt"], 2)
        self.assertEqual(call_counter["flaky"], 2)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from eap.environment import DistributedCoordinator, ToolRegistry
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


ECHO_SCHEMA = {
    "name": "echo",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


class DistributedResiliencePerfTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-dist-resilience-", suffix=".db")
        os.close(fd)
        self.state_manager = StateManager(db_path=self.db_path)
        self.registry = ToolRegistry()
        self.registry.register("echo", lambda value: value, ECHO_SCHEMA)
        self.coordinator = DistributedCoordinator(
            state_manager=self.state_manager,
            registry=self.registry,
            db_path=self.db_path,
            lease_ttl_seconds=1,
        )

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_expired_lease_is_reassigned(self) -> None:
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="s1", tool_name="echo", arguments={"value": "hello"})]
        )
        run_id = self.coordinator.enqueue_macro(macro)
        start_iso = datetime.now(timezone.utc).isoformat()
        first_claim = self.coordinator.claim_work(worker_id="worker-a", now_utc=start_iso)
        self.assertEqual(len(first_claim), 1)
        self.assertEqual(first_claim[0]["attempt"], 1)

        future_iso = (datetime.fromisoformat(start_iso) + timedelta(seconds=5)).isoformat()
        second_claim = self.coordinator.claim_work(worker_id="worker-b", now_utc=future_iso)
        self.assertEqual(len(second_claim), 1)
        self.assertEqual(second_claim[0]["attempt"], 2)
        self.assertEqual(second_claim[0]["step_id"], "s1")

        steps = self.coordinator.list_run_steps(run_id)
        self.assertEqual(steps[0]["attempt"], 2)
        self.assertEqual(steps[0]["status"], "started")

    def test_stale_completion_report_is_rejected_after_reassignment(self) -> None:
        macro = BatchedMacroRequest(
            steps=[ToolCall(step_id="s1", tool_name="echo", arguments={"value": "hello"})]
        )
        self.coordinator.enqueue_macro(macro)
        start_iso = datetime.now(timezone.utc).isoformat()
        first_claim = self.coordinator.claim_work(worker_id="worker-a", now_utc=start_iso)[0]

        future_iso = (datetime.fromisoformat(start_iso) + timedelta(seconds=5)).isoformat()
        second_claim = self.coordinator.claim_work(worker_id="worker-b", now_utc=future_iso)[0]

        stale_completed = self.coordinator.complete_lease(
            lease_id=first_claim["lease_id"],
            worker_id="worker-a",
            output_pointer_id="ptr_old",
        )
        self.assertFalse(stale_completed)

        latest_completed = self.coordinator.complete_lease(
            lease_id=second_claim["lease_id"],
            worker_id="worker-b",
            output_pointer_id="ptr_new",
        )
        self.assertTrue(latest_completed)


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest

from eap.protocol import ExecutionTraceEvent, ExecutionTraceEventType, StateManager


class OperationalMetricsTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-metrics-", suffix=".db")
        os.close(fd)
        self.manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_collect_and_export_metrics(self) -> None:
        self.manager.store_and_point(raw_data={"a": 1}, summary="first")
        self.manager.store_and_point(raw_data={"b": 2}, summary="expiring", ttl_seconds=1)

        session = self.manager.create_session()
        self.manager.append_turn(
            session_id=session["session_id"],
            role="user",
            content="hello metrics",
        )

        run_id = "run_metrics_1"
        self.manager.store_execution_summary(
            run_id=run_id,
            started_at_utc="2026-02-23T00:00:00+00:00",
            completed_at_utc="2026-02-23T00:00:01+00:00",
            total_steps=2,
            succeeded_steps=1,
            failed_steps=1,
            total_duration_ms=1000.0,
            final_pointer_id=None,
        )
        self.manager.append_trace_event(
            ExecutionTraceEvent(
                run_id=run_id,
                step_id="step_1",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.QUEUED,
                attempt=1,
            )
        )

        future_now = "2099-01-01T00:00:00+00:00"
        metrics = self.manager.collect_operational_metrics(now_utc=future_now)
        self.assertEqual(metrics["pointer_store"]["total_pointers"], 2)
        self.assertEqual(metrics["pointer_store"]["active_pointers"], 1)
        self.assertEqual(metrics["pointer_store"]["expired_pointers"], 1)
        self.assertEqual(metrics["conversation"]["session_count"], 1)
        self.assertEqual(metrics["conversation"]["turn_count"], 1)
        self.assertEqual(metrics["execution"]["run_count"], 1)
        self.assertEqual(metrics["execution"]["failed_run_count"], 1)
        self.assertEqual(metrics["execution"]["trace_events_by_type"]["queued"], 1)

        with tempfile.TemporaryDirectory(prefix="eap-metrics-out-") as tmpdir:
            output_path = os.path.join(tmpdir, "latest.json")
            export_info = self.manager.export_operational_metrics(output_path, now_utc=future_now)
            self.assertTrue(os.path.exists(output_path))
            self.assertTrue(export_info["output_path"].endswith("latest.json"))

            payload = json.loads(open(output_path, "r", encoding="utf-8").read())
            self.assertEqual(payload["execution"]["run_count"], 1)
            self.assertEqual(payload["conversation"]["turn_count"], 1)


if __name__ == "__main__":
    unittest.main()

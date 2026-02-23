import unittest

from pydantic import ValidationError

from eap.protocol import (
    ExecutionTraceEvent,
    ExecutionTraceEventType,
    ToolErrorPayload,
)


class TraceModelTests(unittest.TestCase):
    def test_event_type_contract_covers_required_states(self) -> None:
        self.assertEqual(
            {event_type.value for event_type in ExecutionTraceEventType},
            {
                "replayed",
                "queued",
                "approval_required",
                "approved",
                "rejected",
                "started",
                "retried",
                "failed",
                "completed",
            },
        )

    def test_completed_event_requires_output_pointer(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionTraceEvent(
                run_id="run_1",
                step_id="s1",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.COMPLETED,
            )

    def test_failed_event_requires_error_payload(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionTraceEvent(
                run_id="run_1",
                step_id="s2",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.FAILED,
            )

    def test_retried_event_requires_error_and_delay(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionTraceEvent(
                run_id="run_1",
                step_id="s3",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.RETRIED,
                error=ToolErrorPayload(
                    error_type="tool_execution_error",
                    message="timed out",
                    step_id="s3",
                    tool_name="tool_a",
                ),
            )

    def test_valid_completed_event(self) -> None:
        event = ExecutionTraceEvent(
            run_id="run_1",
            step_id="s4",
            tool_name="tool_a",
            event_type=ExecutionTraceEventType.COMPLETED,
            attempt=2,
            duration_ms=123.4,
            output_pointer_id="ptr_abc12345",
        )
        self.assertEqual(event.event_type, ExecutionTraceEventType.COMPLETED)
        self.assertEqual(event.output_pointer_id, "ptr_abc12345")

    def test_rejected_event_requires_error_payload(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionTraceEvent(
                run_id="run_1",
                step_id="s5",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.REJECTED,
            )

    def test_replayed_event_requires_output_pointer(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionTraceEvent(
                run_id="run_1",
                step_id="s6",
                tool_name="tool_a",
                event_type=ExecutionTraceEventType.REPLAYED,
            )


if __name__ == "__main__":
    unittest.main()

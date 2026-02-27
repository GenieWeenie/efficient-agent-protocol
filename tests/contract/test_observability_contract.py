"""Contract tests for the v1 observability surfaces.

These tests enforce the frozen schemas documented in ``docs/v1_contract.md``
under "Observability Contract (Frozen)".
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest

from protocol.logging_config import JsonFormatter, configure_logging
from protocol.models import ExecutionTraceEventType
from protocol.state_manager import StateManager


FROZEN_LOG_REQUIRED_FIELDS = {"timestamp_utc", "level", "logger", "message"}
FROZEN_LOG_OPTIONAL_FIELDS = {"step_id", "tool_name"}

FROZEN_METRICS_TOP_KEYS = {"snapshot_utc", "db_path", "pointer_store", "execution", "conversation"}
FROZEN_POINTER_STORE_KEYS = {"total_pointers", "active_pointers", "expired_pointers"}
FROZEN_EXECUTION_KEYS = {
    "run_count",
    "failed_run_count",
    "total_steps",
    "succeeded_steps",
    "failed_steps",
    "avg_duration_ms",
    "trace_event_total",
    "diagnostics_run_count",
    "trace_events_by_type",
}
FROZEN_CONVERSATION_KEYS = {"session_count", "turn_count"}

FROZEN_TRACE_EVENT_TYPES = {
    "replayed",
    "queued",
    "approval_required",
    "approved",
    "rejected",
    "started",
    "retried",
    "failed",
    "completed",
}


class LogFormatContractTest(unittest.TestCase):
    """Verify structured JSON log format matches the frozen contract."""

    def test_required_fields_present(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=True, stream=stream)
        logger.info("contract-test-message")

        payload = json.loads(stream.getvalue().strip())
        self.assertTrue(
            FROZEN_LOG_REQUIRED_FIELDS.issubset(payload.keys()),
            f"Missing required log fields: {FROZEN_LOG_REQUIRED_FIELDS - payload.keys()}",
        )

    def test_optional_fields_appear_when_set(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=True, stream=stream)
        logger.info(
            "contract-optional",
            extra={"step_id": "s1", "tool_name": "t1"},
        )

        payload = json.loads(stream.getvalue().strip())
        self.assertIn("step_id", payload)
        self.assertIn("tool_name", payload)

    def test_optional_fields_absent_when_not_set(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=True, stream=stream)
        logger.info("contract-no-extras")

        payload = json.loads(stream.getvalue().strip())
        for field in FROZEN_LOG_OPTIONAL_FIELDS:
            self.assertNotIn(field, payload)

    def test_no_unexpected_fields_in_base_log(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=True, stream=stream)
        logger.info("contract-baseline")

        payload = json.loads(stream.getvalue().strip())
        allowed = FROZEN_LOG_REQUIRED_FIELDS | FROZEN_LOG_OPTIONAL_FIELDS
        extra = set(payload.keys()) - allowed
        self.assertEqual(extra, set(), f"Unexpected log fields: {extra}")

    def test_redaction_replaces_secrets(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=True, stream=stream)
        logger.info("api_key=sk-secret token:tok123")

        payload = json.loads(stream.getvalue().strip())
        self.assertIn("[REDACTED]", payload["message"])
        self.assertNotIn("sk-secret", payload["message"])
        self.assertNotIn("tok123", payload["message"])

    def test_level_field_is_standard_name(self) -> None:
        for level_name in ("DEBUG", "INFO", "WARNING", "ERROR"):
            stream = io.StringIO()
            logger = configure_logging(level=level_name, use_json=True, stream=stream)
            getattr(logger, level_name.lower())("level-check")
            payload = json.loads(stream.getvalue().strip())
            self.assertEqual(payload["level"], level_name)


class OperationalMetricsContractTest(unittest.TestCase):
    """Verify operational metrics schema matches the frozen contract."""

    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-obs-contract-", suffix=".db")
        os.close(fd)
        self.manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_top_level_keys_match_contract(self) -> None:
        metrics = self.manager.collect_operational_metrics()
        self.assertTrue(
            FROZEN_METRICS_TOP_KEYS.issubset(metrics.keys()),
            f"Missing top-level metrics keys: {FROZEN_METRICS_TOP_KEYS - metrics.keys()}",
        )

    def test_pointer_store_keys_match_contract(self) -> None:
        metrics = self.manager.collect_operational_metrics()
        actual = set(metrics["pointer_store"].keys())
        self.assertEqual(actual, FROZEN_POINTER_STORE_KEYS)

    def test_execution_keys_match_contract(self) -> None:
        metrics = self.manager.collect_operational_metrics()
        actual = set(metrics["execution"].keys())
        self.assertEqual(actual, FROZEN_EXECUTION_KEYS)

    def test_conversation_keys_match_contract(self) -> None:
        metrics = self.manager.collect_operational_metrics()
        actual = set(metrics["conversation"].keys())
        self.assertEqual(actual, FROZEN_CONVERSATION_KEYS)

    def test_pointer_store_values_are_ints(self) -> None:
        metrics = self.manager.collect_operational_metrics()
        for key in FROZEN_POINTER_STORE_KEYS:
            self.assertIsInstance(metrics["pointer_store"][key], int, f"{key} should be int")

    def test_execution_numeric_types(self) -> None:
        metrics = self.manager.collect_operational_metrics()
        ex = metrics["execution"]
        for key in ("run_count", "failed_run_count", "total_steps", "succeeded_steps",
                     "failed_steps", "trace_event_total", "diagnostics_run_count"):
            self.assertIsInstance(ex[key], int, f"execution.{key} should be int")
        self.assertIsInstance(ex["avg_duration_ms"], float)
        self.assertIsInstance(ex["trace_events_by_type"], dict)

    def test_conversation_values_are_ints(self) -> None:
        metrics = self.manager.collect_operational_metrics()
        for key in FROZEN_CONVERSATION_KEYS:
            self.assertIsInstance(metrics["conversation"][key], int, f"{key} should be int")


class TraceEventTypeContractTest(unittest.TestCase):
    """Verify ExecutionTraceEventType enum values match the frozen contract."""

    def test_all_frozen_values_exist(self) -> None:
        actual = {e.value for e in ExecutionTraceEventType}
        self.assertEqual(actual, FROZEN_TRACE_EVENT_TYPES)

    def test_no_extra_values(self) -> None:
        actual = {e.value for e in ExecutionTraceEventType}
        extra = actual - FROZEN_TRACE_EVENT_TYPES
        self.assertEqual(extra, set(), f"Unexpected trace event types: {extra}")


if __name__ == "__main__":
    unittest.main()

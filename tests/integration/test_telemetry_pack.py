import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import (
    BatchedMacroRequest,
    ExecutionLimits,
    RetryPolicy,
    StateManager,
    ToolCall,
    ToolExecutionLimit,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class _FlakyTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient upstream failure")
        return value


def _slow_tool(value: str) -> str:
    time.sleep(0.02)
    return value


def _always_fail(value: str) -> str:
    raise RuntimeError(f"forced failure:{value}")


def _echo_tool(value: str) -> str:
    return value


TOOL_SCHEMA = {
    "name": "tool_name_placeholder",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    },
}


def _schema_for(name: str) -> dict:
    schema = dict(TOOL_SCHEMA)
    schema["name"] = name
    return schema


class TelemetryPackIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-telemetry-pack-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("flaky_tool", _FlakyTool(), _schema_for("flaky_tool"))
        registry.register("slow_tool", _slow_tool, _schema_for("slow_tool"))
        registry.register("always_fail_tool", _always_fail, _schema_for("always_fail_tool"))
        registry.register("echo_tool", _echo_tool, _schema_for("echo_tool"))
        self.executor = AsyncLocalExecutor(self.state_manager, registry)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_export_telemetry_pack_can_diagnose_failed_run(self) -> None:
        retry_and_saturation_macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="step_flaky", tool_name="flaky_tool", arguments={"value": "ok"}),
                ToolCall(step_id="step_slow_1", tool_name="slow_tool", arguments={"value": "a"}),
                ToolCall(step_id="step_slow_2", tool_name="slow_tool", arguments={"value": "b"}),
                ToolCall(step_id="step_slow_3", tool_name="slow_tool", arguments={"value": "c"}),
            ],
            retry_policy=RetryPolicy(
                max_attempts=2,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
                retryable_error_types=["RuntimeError"],
            ),
            execution_limits=ExecutionLimits(
                max_global_concurrency=4,
                global_requests_per_second=1.0,
                global_burst_capacity=1,
                per_tool={"slow_tool": ToolExecutionLimit(max_concurrency=2)},
            ),
        )
        first_result = asyncio.run(self.executor.execute_macro(retry_and_saturation_macro))
        self.assertIn("pointer_id", first_result)

        failure_macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="step_fail", tool_name="always_fail_tool", arguments={"value": "x"}),
                ToolCall(step_id="step_dep", tool_name="echo_tool", arguments={"value": "$step:step_fail"}),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )
        failure_result = asyncio.run(self.executor.execute_macro(failure_macro))
        failed_run_id = failure_result["metadata"]["execution_run_id"]
        self.assertEqual(failure_result["metadata"]["status"], "error")

        with tempfile.TemporaryDirectory(prefix="eap-telemetry-output-") as temp_dir:
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "export_telemetry_pack.py"),
                "--db-path",
                self.db_path,
                "--output-dir",
                temp_dir,
            ]
            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)

            expected_files = [
                "overview.json",
                "retries.json",
                "fail_reasons.json",
                "latency_percentiles.json",
                "saturation.json",
                "actors.json",
                "failed_run_diagnostics.json",
                "operator_report.md",
                "manifest.json",
            ]
            for filename in expected_files:
                self.assertTrue((Path(temp_dir) / filename).exists(), msg=f"missing {filename}")

            overview = json.loads((Path(temp_dir) / "overview.json").read_text(encoding="utf-8"))
            retries = json.loads((Path(temp_dir) / "retries.json").read_text(encoding="utf-8"))
            fail_reasons = json.loads((Path(temp_dir) / "fail_reasons.json").read_text(encoding="utf-8"))
            saturation = json.loads((Path(temp_dir) / "saturation.json").read_text(encoding="utf-8"))
            actors = json.loads((Path(temp_dir) / "actors.json").read_text(encoding="utf-8"))
            failed_diag = json.loads(
                (Path(temp_dir) / "failed_run_diagnostics.json").read_text(encoding="utf-8")
            )
            report = (Path(temp_dir) / "operator_report.md").read_text(encoding="utf-8")

            self.assertGreaterEqual(overview["run_count"], 2)
            self.assertGreaterEqual(retries["retry_event_total"], 1)
            self.assertGreaterEqual(fail_reasons["failed_event_total"], 1)
            self.assertIn("tool_execution_error", fail_reasons["error_type_counts"])
            self.assertIn("global_rate_wait_seconds", saturation["aggregate"])
            self.assertIn("owner_actor_counts", actors)
            self.assertEqual(failed_diag["failed_run_id"], failed_run_id)
            self.assertEqual(failed_diag["root_failure"]["error_type"], "tool_execution_error")
            self.assertIn("actor_metadata", failed_diag)
            self.assertIn(failed_run_id, report)


if __name__ == "__main__":
    unittest.main()

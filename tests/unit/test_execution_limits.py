import unittest

from pydantic import ValidationError

from eap.protocol import ExecutionLimits, ToolExecutionLimit


class ExecutionLimitsModelTest(unittest.TestCase):
    def test_valid_execution_limits(self) -> None:
        limits = ExecutionLimits(
            max_global_concurrency=4,
            global_requests_per_second=10.0,
            global_burst_capacity=5,
            per_tool={"tool_a": ToolExecutionLimit(max_concurrency=2, requests_per_second=3.0, burst_capacity=2)},
        )
        self.assertEqual(limits.max_global_concurrency, 4)
        self.assertEqual(limits.per_tool["tool_a"].max_concurrency, 2)

    def test_global_burst_requires_global_rps(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionLimits(max_global_concurrency=2, global_burst_capacity=2)

    def test_tool_burst_requires_tool_rps(self) -> None:
        with self.assertRaises(ValidationError):
            ToolExecutionLimit(max_concurrency=1, burst_capacity=2)

    def test_per_tool_key_must_be_non_empty(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionLimits(max_global_concurrency=2, per_tool={"": ToolExecutionLimit(max_concurrency=1)})


if __name__ == "__main__":
    unittest.main()

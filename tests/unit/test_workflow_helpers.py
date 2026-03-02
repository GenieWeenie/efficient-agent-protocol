import unittest

from eap.workflow_helpers import WorkflowBuilder, linear_pipeline
from eap.protocol import BatchedMacroRequest, RetryPolicy, ToolCall


class WorkflowBuilderTest(unittest.TestCase):
    def test_single_step_build(self) -> None:
        wf = WorkflowBuilder().step("s1", "echo", value="hello").build()
        self.assertIsInstance(wf, BatchedMacroRequest)
        self.assertEqual(len(wf.steps), 1)
        self.assertEqual(wf.steps[0].step_id, "s1")
        self.assertEqual(wf.steps[0].tool_name, "echo")
        self.assertEqual(wf.steps[0].arguments, {"value": "hello"})

    def test_multi_step_build(self) -> None:
        wf = (
            WorkflowBuilder()
            .step("fetch", "scrape_url", url="https://example.com")
            .step("analyze", "analyze_data", data="$step:fetch")
            .build()
        )
        self.assertEqual(len(wf.steps), 2)
        self.assertEqual(wf.steps[0].step_id, "fetch")
        self.assertEqual(wf.steps[1].step_id, "analyze")
        self.assertEqual(wf.steps[1].arguments["data"], "$step:fetch")

    def test_with_retry_policy(self) -> None:
        wf = (
            WorkflowBuilder()
            .step("s1", "echo", value="test")
            .with_retry(max_attempts=5, initial_delay=2.0, backoff=3.0, retryable_errors=["TimeoutError"])
            .build()
        )
        self.assertIsNotNone(wf.retry_policy)
        self.assertEqual(wf.retry_policy.max_attempts, 5)
        self.assertEqual(wf.retry_policy.initial_delay_seconds, 2.0)
        self.assertEqual(wf.retry_policy.backoff_multiplier, 3.0)
        self.assertEqual(wf.retry_policy.retryable_error_types, ["TimeoutError"])

    def test_step_references_via_dollar_syntax(self) -> None:
        wf = (
            WorkflowBuilder()
            .step("s1", "tool_a", value="hello")
            .step("s2", "tool_b", input_data="$step:s1")
            .build()
        )
        self.assertEqual(wf.steps[1].arguments["input_data"], "$step:s1")

    def test_build_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowBuilder().build()

    def test_build_without_retry_has_default(self) -> None:
        wf = WorkflowBuilder().step("s1", "echo", value="x").build()
        # retry_policy should use the model default when not set
        self.assertIsNotNone(wf.retry_policy)

    def test_fluent_chaining_returns_self(self) -> None:
        builder = WorkflowBuilder()
        result = builder.step("s1", "echo")
        self.assertIs(result, builder)
        result2 = builder.with_retry()
        self.assertIs(result2, builder)


class LinearPipelineTest(unittest.TestCase):
    def test_single_step_pipeline(self) -> None:
        macro = linear_pipeline([
            {"step_id": "s1", "tool_name": "read_file", "arguments": {"path": "a.txt"}},
        ])
        self.assertEqual(len(macro.steps), 1)
        self.assertEqual(macro.steps[0].step_id, "s1")

    def test_multi_step_pipeline_preserves_order(self) -> None:
        macro = linear_pipeline([
            {"step_id": "s1", "tool_name": "read_file", "arguments": {"path": "a.txt"}},
            {"step_id": "s2", "tool_name": "analyze", "arguments": {"data": "$step:s1"}},
            {"step_id": "s3", "tool_name": "summarize", "arguments": {"data": "$step:s2"}},
        ])
        self.assertEqual(len(macro.steps), 3)
        self.assertEqual(macro.steps[0].step_id, "s1")
        self.assertEqual(macro.steps[1].step_id, "s2")
        self.assertEqual(macro.steps[2].step_id, "s3")
        self.assertEqual(macro.steps[1].arguments["data"], "$step:s1")
        self.assertEqual(macro.steps[2].arguments["data"], "$step:s2")

    def test_with_retry_policy(self) -> None:
        policy = RetryPolicy(max_attempts=2, initial_delay_seconds=0.5, backoff_multiplier=1.5)
        macro = linear_pipeline(
            [{"step_id": "s1", "tool_name": "echo", "arguments": {}}],
            retry_policy=policy,
        )
        self.assertEqual(macro.retry_policy.max_attempts, 2)

    def test_missing_arguments_defaults_empty(self) -> None:
        macro = linear_pipeline([{"step_id": "s1", "tool_name": "noop"}])
        self.assertEqual(macro.steps[0].arguments, {})


if __name__ == "__main__":
    unittest.main()

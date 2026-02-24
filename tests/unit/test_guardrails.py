import unittest

from eap.runtime.guardrails import (
    RUNTIME_OPERATION_MACRO_EXECUTE,
    RUNTIME_OPERATION_RUN_RESUME,
    ConcurrencyLimits,
    RateLimitRule,
    RuntimeGuardrails,
    normalize_concurrency_limits,
    normalize_rate_limit_rules,
)


class RuntimeGuardrailsUnitTest(unittest.TestCase):
    def test_normalize_rate_limit_rules_rejects_unknown_operation(self) -> None:
        with self.assertRaises(ValueError):
            normalize_rate_limit_rules({"unknown_operation": {"max_requests": 1, "window_seconds": 60}})

    def test_rate_limit_blocks_after_max_requests(self) -> None:
        clock_values = [0.0]

        def _clock() -> float:
            return clock_values[0]

        guardrails = RuntimeGuardrails(
            rate_limit_rules={
                RUNTIME_OPERATION_MACRO_EXECUTE: RateLimitRule(max_requests=1, window_seconds=60.0),
                RUNTIME_OPERATION_RUN_RESUME: RateLimitRule(max_requests=1, window_seconds=60.0),
                "run_read": RateLimitRule(max_requests=1, window_seconds=60.0),
                "pointer_summary": RateLimitRule(max_requests=1, window_seconds=60.0),
            },
            clock=_clock,
        )

        first = guardrails.check_rate_limit(operation=RUNTIME_OPERATION_MACRO_EXECUTE, actor_id="actor-1")
        self.assertTrue(first.allowed)
        self.assertEqual(first.remaining, 0)

        second = guardrails.check_rate_limit(operation=RUNTIME_OPERATION_MACRO_EXECUTE, actor_id="actor-1")
        self.assertFalse(second.allowed)
        self.assertGreater(second.retry_after_seconds, 0.0)

    def test_concurrency_limits_block_and_release(self) -> None:
        guardrails = RuntimeGuardrails(
            concurrency_limits=ConcurrencyLimits(
                global_inflight=1,
                execute_inflight=1,
                resume_inflight=1,
                per_run_resume_inflight=1,
            )
        )

        decision_1, token_1 = guardrails.acquire_concurrency(operation=RUNTIME_OPERATION_MACRO_EXECUTE)
        self.assertTrue(decision_1.allowed)
        self.assertIsNotNone(token_1)

        decision_2, token_2 = guardrails.acquire_concurrency(operation=RUNTIME_OPERATION_MACRO_EXECUTE)
        self.assertFalse(decision_2.allowed)
        self.assertIsNone(token_2)
        self.assertEqual(decision_2.limit_type, "global_inflight")

        assert token_1 is not None
        guardrails.release_concurrency(token_1)

        decision_3, token_3 = guardrails.acquire_concurrency(operation=RUNTIME_OPERATION_MACRO_EXECUTE)
        self.assertTrue(decision_3.allowed)
        self.assertIsNotNone(token_3)

    def test_normalize_concurrency_limits_rejects_invalid_value(self) -> None:
        with self.assertRaises(ValueError):
            normalize_concurrency_limits({"global_inflight": 0})


if __name__ == "__main__":
    unittest.main()


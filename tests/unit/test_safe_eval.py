import unittest

from environment.safe_eval import UnsafeExpressionError, evaluate_safe_expression


class SafeExpressionEvaluatorTest(unittest.TestCase):
    def test_allows_basic_boolean_expressions(self) -> None:
        self.assertTrue(evaluate_safe_expression("1501 > 1000"))
        self.assertFalse(evaluate_safe_expression("12 > 1000"))
        self.assertTrue(evaluate_safe_expression("True and not False"))
        self.assertTrue(evaluate_safe_expression("'a' in ['a', 'b']"))

    def test_rejects_non_boolean_result(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("'not-a-bool'")

    def test_rejects_function_calls(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("__import__('os').system('echo pwned') == 0")

    def test_rejects_attribute_access(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("(1).__class__ == int")


if __name__ == "__main__":
    unittest.main()

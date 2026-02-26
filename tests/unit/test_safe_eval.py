import unittest

from environment.safe_eval import (
    MAX_AST_NODES,
    MAX_CONTAINER_ITEMS,
    MAX_EXPRESSION_LENGTH,
    UnsafeExpressionError,
    evaluate_safe_expression,
)


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

    def test_allows_ordered_scalar_comparisons(self) -> None:
        self.assertTrue(evaluate_safe_expression("'abc' < 'abd'"))
        self.assertTrue(evaluate_safe_expression("3 <= 3"))
        self.assertTrue(evaluate_safe_expression("1.5 >= 1.5"))
        self.assertTrue(evaluate_safe_expression("False < True"))

    def test_allows_membership_and_identity_comparisons(self) -> None:
        self.assertTrue(evaluate_safe_expression("'a' in {'a': 1, 'b': 2}"))
        self.assertTrue(evaluate_safe_expression("'x' not in ('a', 'b', 'c')"))
        self.assertTrue(evaluate_safe_expression("None is None"))
        self.assertTrue(evaluate_safe_expression("None is not True"))

    def test_rejects_ordered_mismatched_types(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("1 < 1.0")
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("'1' < 1")

    def test_rejects_invalid_membership_rhs(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("1 in 1")

    def test_rejects_set_literals_with_nested_values(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("[1] in {[1], [2]}")

    def test_rejects_dict_unpacking(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("{**{'a': 1}} == {'a': 1}")

    def test_rejects_invalid_expression_length(self) -> None:
        expression = "x" * (MAX_EXPRESSION_LENGTH + 1)
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression(expression)

    def test_rejects_invalid_syntax(self) -> None:
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression("1 <")

    def test_rejects_overly_complex_expression(self) -> None:
        expression = " and ".join(["True"] * (MAX_AST_NODES + 1))
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression(expression)

    def test_rejects_oversized_container_literals(self) -> None:
        oversized = ",".join(str(i) for i in range(MAX_CONTAINER_ITEMS + 1))
        with self.assertRaises(UnsafeExpressionError):
            evaluate_safe_expression(f"[{oversized}] == [{oversized}]")


if __name__ == "__main__":
    unittest.main()

import ast
from typing import Any


MAX_EXPRESSION_LENGTH = 2048
MAX_AST_NODES = 256
MAX_CONTAINER_ITEMS = 128


class UnsafeExpressionError(ValueError):
    """Raised when a branch expression contains unsupported/unsafe constructs."""


class _SafeExpressionValidator(ast.NodeVisitor):
    _ALLOWED_COMPARE_OPS = (
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
    )
    _ALLOWED_BOOL_OPS = (ast.And, ast.Or)
    _ALLOWED_UNARY_OPS = (ast.Not,)
    _ALLOWED_CONTAINER_NODES = (ast.List, ast.Tuple, ast.Set, ast.Dict)
    _ALLOWED_LITERAL_TYPES = (str, int, float, bool, type(None))

    def __init__(self, max_nodes: int = MAX_AST_NODES) -> None:
        self.max_nodes = max_nodes
        self.node_count = 0

    def visit(self, node: ast.AST) -> Any:
        self.node_count += 1
        if self.node_count > self.max_nodes:
            raise UnsafeExpressionError("Branch expression is too complex.")
        return super().visit(node)

    def generic_visit(self, node: ast.AST) -> Any:
        allowed_nodes = (
            ast.Expression,
            ast.Constant,
            ast.BoolOp,
            ast.UnaryOp,
            ast.Compare,
            ast.Load,
            *self._ALLOWED_CONTAINER_NODES,
            *self._ALLOWED_COMPARE_OPS,
            *self._ALLOWED_BOOL_OPS,
            *self._ALLOWED_UNARY_OPS,
        )
        if not isinstance(node, allowed_nodes):
            raise UnsafeExpressionError(
                f"Unsupported branch expression construct: {node.__class__.__name__}."
            )
        return super().generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if not isinstance(node.value, self._ALLOWED_LITERAL_TYPES):
            raise UnsafeExpressionError(
                f"Unsupported literal type in branch expression: {type(node.value).__name__}."
            )

    def visit_BoolOp(self, node: ast.BoolOp) -> None:  # noqa: N802
        if not isinstance(node.op, self._ALLOWED_BOOL_OPS):
            raise UnsafeExpressionError("Unsupported boolean operator in branch expression.")
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:  # noqa: N802
        if not isinstance(node.op, self._ALLOWED_UNARY_OPS):
            raise UnsafeExpressionError("Unsupported unary operator in branch expression.")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        for op in node.ops:
            if not isinstance(op, self._ALLOWED_COMPARE_OPS):
                raise UnsafeExpressionError("Unsupported comparison operator in branch expression.")
        self.generic_visit(node)


def _evaluate_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.List):
        if len(node.elts) > MAX_CONTAINER_ITEMS:
            raise UnsafeExpressionError("Branch list literal exceeds max item limit.")
        return [_evaluate_node(elt) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        if len(node.elts) > MAX_CONTAINER_ITEMS:
            raise UnsafeExpressionError("Branch tuple literal exceeds max item limit.")
        return tuple(_evaluate_node(elt) for elt in node.elts)

    if isinstance(node, ast.Set):
        if len(node.elts) > MAX_CONTAINER_ITEMS:
            raise UnsafeExpressionError("Branch set literal exceeds max item limit.")
        return {_evaluate_node(elt) for elt in node.elts}

    if isinstance(node, ast.Dict):
        if len(node.keys) > MAX_CONTAINER_ITEMS:
            raise UnsafeExpressionError("Branch dict literal exceeds max item limit.")
        return {
            _evaluate_node(key): _evaluate_node(value)
            for key, value in zip(node.keys, node.values)
        }

    if isinstance(node, ast.BoolOp):
        values = [_evaluate_node(value) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(bool(value) for value in values)
        if isinstance(node.op, ast.Or):
            return any(bool(value) for value in values)
        raise UnsafeExpressionError("Unsupported boolean operator in branch expression.")

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not bool(_evaluate_node(node.operand))
        raise UnsafeExpressionError("Unsupported unary operator in branch expression.")

    if isinstance(node, ast.Compare):
        left = _evaluate_node(node.left)
        for operator, comparator in zip(node.ops, node.comparators):
            right = _evaluate_node(comparator)
            if isinstance(operator, ast.Eq):
                outcome = left == right
            elif isinstance(operator, ast.NotEq):
                outcome = left != right
            elif isinstance(operator, ast.Lt):
                outcome = left < right
            elif isinstance(operator, ast.LtE):
                outcome = left <= right
            elif isinstance(operator, ast.Gt):
                outcome = left > right
            elif isinstance(operator, ast.GtE):
                outcome = left >= right
            elif isinstance(operator, ast.In):
                outcome = left in right
            elif isinstance(operator, ast.NotIn):
                outcome = left not in right
            elif isinstance(operator, ast.Is):
                outcome = left is right
            elif isinstance(operator, ast.IsNot):
                outcome = left is not right
            else:
                raise UnsafeExpressionError("Unsupported comparison operator in branch expression.")

            if not outcome:
                return False
            left = right
        return True

    raise UnsafeExpressionError(f"Unsupported expression node: {node.__class__.__name__}.")


def evaluate_safe_expression(expression: str) -> bool:
    if not isinstance(expression, str) or not expression.strip():
        raise UnsafeExpressionError("Branch expression must be a non-empty string.")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError(
            f"Branch expression length exceeds limit ({MAX_EXPRESSION_LENGTH})."
        )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError("Branch expression is not valid syntax.") from exc

    _SafeExpressionValidator().visit(tree)
    result = _evaluate_node(tree.body)
    if not isinstance(result, bool):
        raise UnsafeExpressionError("Branch expression must evaluate to a boolean value.")
    return result

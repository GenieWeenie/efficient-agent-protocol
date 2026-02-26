import ast
from typing import TypeAlias, cast


MAX_EXPRESSION_LENGTH = 2048
MAX_AST_NODES = 256
MAX_CONTAINER_ITEMS = 128


class UnsafeExpressionError(ValueError):
    """Raised when a branch expression contains unsupported/unsafe constructs."""


ExpressionPrimitive: TypeAlias = str | int | float | bool | None
ExpressionScalar: TypeAlias = str | int | float | bool
ExpressionValue: TypeAlias = (
    ExpressionPrimitive
    | list["ExpressionValue"]
    | tuple["ExpressionValue", ...]
    | set[ExpressionPrimitive]
    | dict[ExpressionPrimitive, "ExpressionValue"]
)


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

    def visit(self, node: ast.AST) -> object:
        self.node_count += 1
        if self.node_count > self.max_nodes:
            raise UnsafeExpressionError("Branch expression is too complex.")
        return super().visit(node)

    def generic_visit(self, node: ast.AST) -> object:
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

    def visit_Dict(self, node: ast.Dict) -> None:  # noqa: N802
        if any(key is None for key in node.keys):
            raise UnsafeExpressionError("Dict unpacking is not supported in branch expressions.")
        self.generic_visit(node)


def _to_scalar(value: ExpressionValue) -> ExpressionScalar:
    if not isinstance(value, (int, float, str, bool)):
        raise UnsafeExpressionError("Ordered comparisons require scalar operands.")
    return value


def _evaluate_ordered_comparison(operator: ast.AST, left: ExpressionValue, right: ExpressionValue) -> bool:
    left_scalar = _to_scalar(left)
    right_scalar = _to_scalar(right)
    if type(left_scalar) is not type(right_scalar):
        raise UnsafeExpressionError("Ordered comparisons require matching operand types.")

    if isinstance(left_scalar, str):
        right_str = cast(str, right_scalar)
        if isinstance(operator, ast.Lt):
            return bool(left_scalar < right_str)
        if isinstance(operator, ast.LtE):
            return bool(left_scalar <= right_str)
        if isinstance(operator, ast.Gt):
            return bool(left_scalar > right_str)
        if isinstance(operator, ast.GtE):
            return bool(left_scalar >= right_str)
        raise UnsafeExpressionError("Unsupported ordered comparison operator.")
    elif isinstance(left_scalar, bool):
        right_bool = cast(bool, right_scalar)
        if isinstance(operator, ast.Lt):
            return bool(left_scalar < right_bool)
        if isinstance(operator, ast.LtE):
            return bool(left_scalar <= right_bool)
        if isinstance(operator, ast.Gt):
            return bool(left_scalar > right_bool)
        if isinstance(operator, ast.GtE):
            return bool(left_scalar >= right_bool)
        raise UnsafeExpressionError("Unsupported ordered comparison operator.")
    elif isinstance(left_scalar, int):
        right_int = cast(int, right_scalar)
        if isinstance(operator, ast.Lt):
            return bool(left_scalar < right_int)
        if isinstance(operator, ast.LtE):
            return bool(left_scalar <= right_int)
        if isinstance(operator, ast.Gt):
            return bool(left_scalar > right_int)
        if isinstance(operator, ast.GtE):
            return bool(left_scalar >= right_int)
        raise UnsafeExpressionError("Unsupported ordered comparison operator.")
    elif isinstance(left_scalar, float):
        right_float = cast(float, right_scalar)
        if isinstance(operator, ast.Lt):
            return bool(left_scalar < right_float)
        if isinstance(operator, ast.LtE):
            return bool(left_scalar <= right_float)
        if isinstance(operator, ast.Gt):
            return bool(left_scalar > right_float)
        if isinstance(operator, ast.GtE):
            return bool(left_scalar >= right_float)
        raise UnsafeExpressionError("Unsupported ordered comparison operator.")
    else:  # pragma: no cover - guarded by _to_scalar
        raise UnsafeExpressionError("Ordered comparisons require scalar operands.")


def _evaluate_membership(operator: ast.AST, left: ExpressionValue, right: ExpressionValue) -> bool:
    if not isinstance(right, (list, tuple, set, dict, str)):
        raise UnsafeExpressionError("Membership comparisons require container/string right operand.")
    if isinstance(operator, ast.In):
        return bool(left in right)
    if isinstance(operator, ast.NotIn):
        return bool(left not in right)
    raise UnsafeExpressionError("Unsupported membership comparison operator.")


def _evaluate_node(node: ast.AST) -> ExpressionValue:
    if isinstance(node, ast.Constant):
        const_value = node.value
        if not isinstance(const_value, (str, int, float, bool, type(None))):
            raise UnsafeExpressionError(
                f"Unsupported literal type in branch expression: {type(const_value).__name__}."
            )
        return const_value

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
        values = {_evaluate_node(elt) for elt in node.elts}
        if not all(isinstance(value, (str, int, float, bool, type(None))) for value in values):
            raise UnsafeExpressionError("Set literals only support scalar/None values.")
        return cast(set[ExpressionPrimitive], values)

    if isinstance(node, ast.Dict):
        if len(node.keys) > MAX_CONTAINER_ITEMS:
            raise UnsafeExpressionError("Branch dict literal exceeds max item limit.")
        result: dict[ExpressionPrimitive, ExpressionValue] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                raise UnsafeExpressionError("Dict unpacking is not supported in branch expressions.")
            resolved_key = _evaluate_node(key_node)
            if not isinstance(resolved_key, (str, int, float, bool, type(None))):
                raise UnsafeExpressionError("Dict keys must be scalar/None values.")
            result[resolved_key] = _evaluate_node(value_node)
        return result

    if isinstance(node, ast.BoolOp):
        bool_values = [_evaluate_node(value_node) for value_node in node.values]
        if isinstance(node.op, ast.And):
            return all(bool(value) for value in bool_values)
        if isinstance(node.op, ast.Or):
            return any(bool(value) for value in bool_values)
        raise UnsafeExpressionError("Unsupported boolean operator in branch expression.")

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not bool(_evaluate_node(node.operand))
        raise UnsafeExpressionError("Unsupported unary operator in branch expression.")

    if isinstance(node, ast.Compare):
        left: ExpressionValue = _evaluate_node(node.left)
        for operator, comparator in zip(node.ops, node.comparators):
            right: ExpressionValue = _evaluate_node(comparator)
            if isinstance(operator, ast.Eq):
                outcome = left == right
            elif isinstance(operator, ast.NotEq):
                outcome = left != right
            elif isinstance(operator, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                outcome = _evaluate_ordered_comparison(operator, left, right)
            elif isinstance(operator, (ast.In, ast.NotIn)):
                outcome = _evaluate_membership(operator, left, right)
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

"""A per-pixel math expression, the cheapest way to make something wild.

Checked against a whitelist before running, because the expression can come from a model.
"""

from __future__ import annotations

import ast
import math
from typing import Callable

from .patterns import noise

MAX_LENGTH = 400

_FUNCTIONS: dict[str, Callable] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "atan": math.atan, "atan2": math.atan2,
    "sqrt": lambda v: math.sqrt(abs(v)), "abs": abs, "floor": math.floor, "ceil": math.ceil,
    "exp": math.exp, "log": lambda v: math.log(abs(v) + 1e-9), "hypot": math.hypot, "min": min,
    "max": max, "round": round, "noise": noise, "int": int, "pow": lambda a, b: abs(a) ** b,
}
_CONSTANTS = {"pi": math.pi, "tau": math.tau, "e": math.e}
_NAMES = {"x", "y", "u", "v", "r", "a", "W", "H"} | set(_FUNCTIONS) | set(_CONSTANTS)
_ALLOWED = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Call, ast.Name,
    ast.Load, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    ast.BitXor, ast.BitAnd, ast.BitOr,
)


class FormulaError(ValueError):
    pass


def compile_formula(source: str) -> Callable[[int, int, int, int], bool]:
    """Returns f(x, y, W, H) -> is this pixel black."""
    if len(source) > MAX_LENGTH:
        raise FormulaError(f"Formula is over {MAX_LENGTH} characters.")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Formula has a syntax error: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise FormulaError(f"{type(node).__name__} isn't allowed in a formula.")
        if isinstance(node, ast.Name) and node.id not in _NAMES:
            raise FormulaError(f"Unknown name {node.id!r} in formula.")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS):
            raise FormulaError("Only the built-in functions can be called.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise FormulaError("Only numbers are allowed in a formula.")

    code = compile(tree, "<formula>", "eval")
    env: dict = {"__builtins__": {}, **_FUNCTIONS, **_CONSTANTS}

    def evaluate(x: int, y: int, width: int, height: int) -> bool:
        cx, cy = x - width / 2, y - height / 2
        env.update(x=x, y=y, W=width, H=height, u=x / max(width - 1, 1), v=y / max(height - 1, 1), r=math.hypot(cx, cy), a=math.atan2(cy, cx))
        try:
            return bool(eval(code, env))  # noqa: S307 - the tree was checked against the whitelist.
        except (ArithmeticError, ValueError, TypeError):
            return False

    return evaluate

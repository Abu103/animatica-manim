"""Safety checks for untrusted (LLM-written) input: LaTeX denylist and a restricted function parser."""
from __future__ import annotations

import ast
import math
from typing import Callable

from animatica.storyboard.models import MAX_TEXT

LATEX_DENYLIST = (r"\write18", r"\input", r"\include", r"\openin", r"\openout", r"\immediate", r"\catcode")
_FUNCS: dict[str, Callable[[float], float]] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
    "log": math.log, "sqrt": math.sqrt, "abs": abs,
}
_NAMES = {"pi": math.pi, "e": math.e}
_MAX_DEPTH = 40


class UnsafeInput(ValueError):
    """Raised when LaTeX or an expression contains something outside the allowlist."""


def check_latex(s: str) -> None:
    if len(s) > MAX_TEXT:
        raise UnsafeInput(f"LaTeX string is longer than {MAX_TEXT} characters")
    for seq in LATEX_DENYLIST:
        if seq in s:
            raise UnsafeInput(f"LaTeX contains a blocked command: {seq}")


def latex_braces_balanced(s: str) -> bool:
    """True if every `{` has a matching `}` (escaped `\\{` and `\\}` are ignored)."""
    depth, i = 0, 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


def _validate(node: ast.AST, depth: int = 0, var_name: str = "x") -> None:
    if depth > _MAX_DEPTH:
        raise UnsafeInput("Expression is nested too deeply")
    if isinstance(node, ast.Expression):
        _validate(node.body, depth + 1, var_name=var_name)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        _validate(node.left, depth + 1, var_name=var_name)
        _validate(node.right, depth + 1, var_name=var_name)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        _validate(node.operand, depth + 1, var_name=var_name)
    elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return
    elif isinstance(node, ast.Name) and (node.id == var_name or node.id in _NAMES):
        return
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
          and len(node.args) == 1 and not node.keywords):
        _validate(node.args[0], depth + 1, var_name=var_name)
    else:
        raise UnsafeInput(f"Not allowed in a function expression: {type(node).__name__}")


def _eval(node: ast.AST, x: float, var_name: str = "x") -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, x, var_name=var_name)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return x if node.id == var_name else _NAMES[node.id]
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, x, var_name=var_name)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, x, var_name=var_name), _eval(node.right, x, var_name=var_name)
        op = node.op
        if isinstance(op, ast.Add):
            return a + b
        if isinstance(op, ast.Sub):
            return a - b
        if isinstance(op, ast.Mult):
            return a * b
        if isinstance(op, ast.Div):
            return a / b
        return math.pow(a, b)
    if isinstance(node, ast.Call):
        return _FUNCS[node.func.id](_eval(node.args[0], x, var_name=var_name))  # type: ignore[attr-defined]
    raise UnsafeInput("unreachable")  # pragma: no cover


def parse_function(expr: str, var_name: str = "x") -> Callable[[float], float]:
    """Parse `expr` (variable `var_name`) into a callable. Domain errors return NaN. Never uses eval."""
    if len(expr) > MAX_TEXT:
        raise UnsafeInput(f"Expression is longer than {MAX_TEXT} characters")
    try:
        tree = ast.parse(expr.replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise UnsafeInput(f"Could not read the expression {expr!r}: {exc.msg}") from exc
    _validate(tree, var_name=var_name)

    def fn(t: float) -> float:
        try:
            return _eval(tree, float(t), var_name=var_name)
        except (ZeroDivisionError, ValueError, OverflowError):
            return math.nan

    return fn


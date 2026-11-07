"""Safe text handling for the 3-SAT HyperFrames pilot.

All user-supplied text is escaped for HTML attribute and text contexts.
No raw HTML, JavaScript, paths, or shell commands can be injected.
"""
from __future__ import annotations

_HTML_ESCAPE_TABLE = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#x27;",
    "/": "&#x2F;",
    "`": "&#x60;",
    "=": "&#x3D;",
}


def escape_html(text: str) -> str:
    """Escape a string for safe insertion as HTML text content.

    Replaces &, <, >, ", ', /, `, = with their entity equivalents.
    Never returns markup that could be parsed as HTML or JS.
    """
    return "".join(_HTML_ESCAPE_TABLE.get(ch, ch) for ch in text)


def escape_attr(text: str) -> str:
    """Escape a string for safe insertion as an HTML attribute value.

    Same escaping as escape_html; attribute context adds no extra risk
    since all dangerous characters are already neutralized.
    """
    return escape_html(text)


def format_variable_label(var_id: str, subscript: bool = True) -> str:
    """Format a variable id as a safe display label.

    var_id must already be validated as matching ^[xX][1-3]$.
    Optionally renders with a Unicode subscript digit.
    """
    sub_map = {"1": "\u2081", "2": "\u2082", "3": "\u2083"}
    num = var_id[1] if len(var_id) > 1 else var_id
    if subscript and num in sub_map:
        return f"x{sub_map[num]}"
    return f"x{escape_html(num)}"


def format_literal_label(var_id: str, negated: bool) -> str:
    """Format a literal label as safe HTML text.

    Returns something like "x\u2081" or "NOT x\u2082".
    """
    label = format_variable_label(var_id)
    if negated:
        return f"NOT {label}"
    return label


def format_case_label(case_label: str) -> str:
    """Escape a case label for display."""
    return escape_html(case_label)


def format_truth(value: bool) -> tuple[str, str]:
    """Return (icon, word) for a boolean value.

    Uses words AND symbols, never color alone, to distinguish true/false.
    """
    if value:
        return ("\u2713", "TRUE")   # checkmark + TRUE
    return ("\u00D7", "FALSE")      # multiplication sign (×) + FALSE

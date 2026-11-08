"""Safe text handling for the binary search HyperFrames pilot.

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


def format_truth(value: bool) -> tuple[str, str]:
    """Return (icon, word) for a boolean value.

    Uses words AND symbols, never color alone, to distinguish true/false.
    """
    if value:
        return ("\u2713", "TRUE")   # checkmark + TRUE
    return ("\u00D7", "FALSE")      # multiplication sign (×) + FALSE


def format_step_label(low: int, high: int, mid: int) -> str:
    """Format a search-range label for display."""
    return f"{low}\u2013{high}  mid={mid}"

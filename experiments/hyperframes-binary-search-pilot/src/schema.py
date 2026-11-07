"""Schema validation for binary search HyperFrames pilot input data.

Validates a minimal, bounded data model:
- A sorted list of integers (the array to search)
- One integer target value
- A short case label
- No arbitrary HTML, JS, paths, or shell commands in any text field
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Schema constants (bounded)
# ---------------------------------------------------------------------------

_MAX_ARRAY_LEN = 64
_MAX_CASE_LABEL_LEN = 80

_TEXT_RE = re.compile(r"^[A-Za-z0-9_\u00B2\u00B3\u2081\u2082\u2083\s.\u2022\u2026\-]+$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9_\u00B2\u00B3\u2081\u2082\u2083\s.\u2022\u2026\-]+$")


class SchemaError(ValueError):
    """Raised when input data violates the binary search pilot schema."""


def _require_dict(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise SchemaError(f"{field}: expected object, got {type(value).__name__}")
    return value


def _require_int(value: Any, field: str, minimum: int | None = None, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SchemaError(f"{field}: expected integer, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise SchemaError(f"{field}: expected >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise SchemaError(f"{field}: expected <= {maximum}, got {value}")
    return value


def _require_str(value: Any, field: str, pattern: re.Pattern, max_len: int = 80) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{field}: expected string, got {type(value).__name__}")
    if len(value) == 0 or len(value) > max_len:
        raise SchemaError(f"{field}: length must be 1..{max_len}, got {len(value)}")
    if not pattern.match(value):
        raise SchemaError(f"{field}: contains disallowed characters: {value!r}")
    return value


def _require_int_list(value: Any, field: str, min_len: int = 1, max_len: int = _MAX_ARRAY_LEN) -> list[int]:
    if not isinstance(value, list):
        raise SchemaError(f"{field}: expected array")
    if len(value) < min_len or len(value) > max_len:
        raise SchemaError(f"{field}: length must be {min_len}..{max_len}, got {len(value)}")
    result: list[int] = []
    for i, item in enumerate(value):
        if not isinstance(item, int) or isinstance(item, bool):
            raise SchemaError(f"{field}[{i}]: expected integer, got {type(item).__name__}")
        result.append(item)
    return result


def validate_binary_search_data(data: Any) -> dict[str, Any]:
    """Validate the complete binary search pilot input and return a normalized dict.

    Rejects: extra top-level keys, wrong types, missing fields,
    unsorted arrays, empty arrays, non-integer targets.
    """
    if not isinstance(data, dict):
        raise SchemaError("pilot data: expected object")

    allowed_top = {"array", "target", "case_label"}
    extra = set(data.keys()) - allowed_top
    if extra:
        raise SchemaError(f"unexpected top-level keys: {sorted(extra)}")

    array = _require_int_list(data.get("array", []), "array")

    # Verify sorted ascending (strictly increasing)
    for i in range(1, len(array)):
        if array[i] <= array[i - 1]:
            raise SchemaError(
                f"array: must be strictly ascending; element {i} ({array[i]}) "
                f"not greater than element {i-1} ({array[i-1]})"
            )

    target = _require_int(data.get("target"), "target")
    case_label = _require_str(data.get("case_label", ""), "case_label", _LABEL_RE)

    return {
        "array": array,
        "target": target,
        "case_label": case_label,
    }

"""Schema validation for 3-SAT HyperFrames pilot input data.

Validates a minimal, bounded data model:
- Exactly three Boolean variables
- Two OR clauses, each with exactly three literals
- Each literal references a known variable, optionally negated
- One assignment mapping each variable to a Boolean value
- No arbitrary HTML, JS, paths, or shell commands in any text field
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Schema constants (bounded)
# ---------------------------------------------------------------------------

VARIABLE_COUNT = 3
CLAUSE_COUNT = 2
LITERALS_PER_CLAUSE = 3

_VAR_ID_RE = re.compile(r"^[xX][1-3]$")
_TEXT_RE = re.compile(r"^[A-Za-z0-9_\u00B2\u00B3\u2081\u2082\u2083\s\.\u2022\u2026\-]+$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9\u00B2\u00B3\u2081\u2082\u2083\s\.\u2022\u2026\-]+$")


class SchemaError(ValueError):
    """Raised when input data violates the 3-SAT pilot schema."""


def _require_dict(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise SchemaError(f"{field}: expected object, got {type(value).__name__}")
    return value


def _require_str(value: Any, field: str, pattern: re.Pattern, max_len: int = 80) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{field}: expected string, got {type(value).__name__}")
    if len(value) == 0 or len(value) > max_len:
        raise SchemaError(f"{field}: length must be 1..{max_len}, got {len(value)}")
    if not pattern.match(value):
        raise SchemaError(f"{field}: contains disallowed characters: {value!r}")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaError(f"{field}: expected boolean, got {type(value).__name__}")
    return value


def _require_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SchemaError(f"{field}: expected integer, got {type(value).__name__}")
    if value < minimum or value > maximum:
        raise SchemaError(f"{field}: expected {minimum}..{maximum}, got {value}")
    return value


def validate_variables(raw: Any) -> list[dict[str, str]]:
    """Validate the variables array: exactly 3, ids x1/x2/x3, short labels."""
    if not isinstance(raw, list):
        raise SchemaError("variables: expected array")
    if len(raw) != VARIABLE_COUNT:
        raise SchemaError(f"variables: expected exactly {VARIABLE_COUNT}, got {len(raw)}")
    expected_ids = [f"x{i+1}" for i in range(VARIABLE_COUNT)]
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for i, entry in enumerate(raw):
        obj = _require_dict(entry, f"variables[{i}]")
        var_id = _require_str(obj.get("id", ""), f"variables[{i}].id", _VAR_ID_RE)
        if var_id != expected_ids[i]:
            raise SchemaError(
                f"variables[{i}].id: expected {expected_ids[i]!r}, got {var_id!r}"
            )
        if var_id in seen:
            raise SchemaError(f"variables: duplicate id {var_id!r}")
        seen.add(var_id)
        label = _require_str(obj.get("label", ""), f"variables[{i}].label", _LABEL_RE)
        result.append({"id": var_id, "label": label})
    return result


def validate_clauses(
    raw: Any, var_ids: list[str]
) -> list[dict[str, Any]]:
    """Validate the clauses array: exactly 2, each with exactly 3 literals."""
    if not isinstance(raw, list):
        raise SchemaError("clauses: expected array")
    if len(raw) != CLAUSE_COUNT:
        raise SchemaError(f"clauses: expected exactly {CLAUSE_COUNT}, got {len(raw)}")
    var_set = set(var_ids)
    result: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        obj = _require_dict(entry, f"clauses[{i}]")
        clause_id = _require_str(obj.get("id", ""), f"clauses[{i}].id", re.compile(r"^[a-z0-9]+$"))
        label = _require_str(obj.get("label", ""), f"clauses[{i}].label", _LABEL_RE)
        rule = _require_str(obj.get("rule", ""), f"clauses[{i}].rule", _TEXT_RE)
        literals_raw = obj.get("literals", [])
        if not isinstance(literals_raw, list):
            raise SchemaError(f"clauses[{i}].literals: expected array")
        if len(literals_raw) != LITERALS_PER_CLAUSE:
            raise SchemaError(
                f"clauses[{i}].literals: expected exactly {LITERALS_PER_CLAUSE}, "
                f"got {len(literals_raw)}"
            )
        literals: list[dict[str, Any]] = []
        seen_vars: set[str] = set()
        for j, lit in enumerate(literals_raw):
            lit_obj = _require_dict(lit, f"clauses[{i}].literals[{j}]")
            var = lit_obj.get("var", "")
            if not isinstance(var, str) or var not in var_set:
                raise SchemaError(
                    f"clauses[{i}].literals[{j}].var: must be one of {sorted(var_set)}, "
                    f"got {var!r}"
                )
            if var in seen_vars:
                raise SchemaError(
                    f"clauses[{i}].literals[{j}].var: duplicate variable {var!r} in same clause"
                )
            seen_vars.add(var)
            negated = _require_bool(lit_obj.get("negated", False), f"clauses[{i}].literals[{j}].negated")
            literals.append({"var": var, "negated": negated})
        result.append({"id": clause_id, "label": label, "rule": rule, "literals": literals})
    return result


def validate_assignment(raw: Any, var_ids: list[str]) -> dict[str, bool]:
    """Validate the assignment: exactly the 3 variable ids, each a bool."""
    obj = _require_dict(raw, "assignment")
    result: dict[str, bool] = {}
    for vid in var_ids:
        if vid not in obj:
            raise SchemaError(f"assignment: missing variable {vid!r}")
        result[vid] = _require_bool(obj[vid], f"assignment.{vid}")
    extra = set(obj.keys()) - set(var_ids)
    if extra:
        raise SchemaError(f"assignment: unexpected variables {sorted(extra)}")
    return result


def validate_case_label(raw: Any) -> str:
    if not isinstance(raw, str):
        raise SchemaError("case_label: expected string")
    return _require_str(raw, "case_label", _TEXT_RE)


def validate_pilot_data(data: Any) -> dict[str, Any]:
    """Validate the complete pilot input and return a normalized dict.

    Rejects: extra top-level keys, wrong types, missing fields, duplicate IDs,
    unknown variable references, negated non-bool, non-boolean assignment values.
    """
    if not isinstance(data, dict):
        raise SchemaError("pilot data: expected object")

    allowed_top = {"variables", "clauses", "assignment", "case_label"}
    extra = set(data.keys()) - allowed_top
    if extra:
        raise SchemaError(f"unexpected top-level keys: {sorted(extra)}")

    variables = validate_variables(data.get("variables", []))
    var_ids = [v["id"] for v in variables]
    clauses = validate_clauses(data.get("clauses", []), var_ids)
    assignment = validate_assignment(data.get("assignment", {}), var_ids)
    case_label = validate_case_label(data.get("case_label", ""))

    return {
        "variables": variables,
        "clauses": clauses,
        "assignment": assignment,
        "case_label": case_label,
    }


# ---------------------------------------------------------------------------
# Boolean evaluation (independent of rendering)
# ---------------------------------------------------------------------------

def evaluate_literal(assignment: dict[str, bool], var: str, negated: bool) -> bool:
    """Compute a literal's truth value from the assignment and negation flag."""
    return (not assignment[var]) if negated else assignment[var]


def evaluate_clause(literal_values: list[bool]) -> bool:
    """OR: true if at least one literal is true."""
    return any(literal_values)


def evaluate_formula(clause_values: list[bool]) -> bool:
    """AND: true only if all clauses are true."""
    return all(clause_values)


def evaluate_all(
    validated: dict[str, Any],
) -> dict[str, Any]:
    """Compute literal, clause, and formula truth values from validated data.

    Returns a dict with:
      - literal_values: list of 6 booleans (clause-major order)
      - clause_values: list of 2 booleans
      - formula_value: single boolean
    """
    assignment = validated["assignment"]
    clauses = validated["clauses"]

    literal_values: list[bool] = []
    for clause in clauses:
        for lit in clause["literals"]:
            literal_values.append(
                evaluate_literal(assignment, lit["var"], lit["negated"])
            )

    clause_values = [
        evaluate_clause(literal_values[0:3]),
        evaluate_clause(literal_values[3:6]),
    ]
    formula_value = evaluate_formula(clause_values)

    return {
        "literal_values": literal_values,
        "clause_values": clause_values,
        "formula_value": formula_value,
    }

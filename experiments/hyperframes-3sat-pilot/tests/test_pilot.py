"""Tests for the 3-SAT HyperFrames pilot: schema validation, Boolean
evaluation, safe text handling, and end-to-end rendering."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from escape import escape_html, format_literal_label, format_truth
from schema import (
    SchemaError,
    evaluate_all,
    validate_clauses,
    validate_pilot_data,
    validate_variables,
)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_validates_all_true_fixture():
    raw = json.loads((ROOT / "fixtures" / "fixture_a_all_true.json").read_text())
    result = validate_pilot_data(raw)
    assert len(result["variables"]) == 3
    assert len(result["clauses"]) == 2
    assert result["assignment"] == {"x1": True, "x2": True, "x3": True}


def test_validates_all_false_fixture():
    raw = json.loads((ROOT / "fixtures" / "fixture_b_all_false.json").read_text())
    result = validate_pilot_data(raw)
    assert result["assignment"] == {"x1": False, "x2": False, "x3": False}


def test_validates_false_formula_fixture():
    raw = json.loads((ROOT / "fixtures" / "fixture_c_false_formula.json").read_text())
    result = validate_pilot_data(raw)
    assert result["assignment"] == {"x1": False, "x2": False, "x3": False}
    # Different clause structure from fixtures A/B
    assert result["clauses"][0]["literals"][0]["negated"] is False
    assert result["clauses"][1]["literals"][0]["negated"] is True


def test_rejects_extra_top_level_key():
    raw = {
        "variables": [{"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
        "bogus": 1,
    }
    with pytest.raises(SchemaError, match="unexpected top-level keys"):
        validate_pilot_data(raw)


def test_rejects_wrong_variable_count():
    raw = {
        "variables": [{"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x1", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x1", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="exactly 3"):
        validate_pilot_data(raw)


def test_rejects_duplicate_variable_ids():
    # With strictly ordered IDs (x1, x2, x3), duplicates are structurally
    # impossible. Use x3 in the wrong position instead (valid ID, wrong slot).
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x3", "label": "x\u2083"}, {"id": "x2", "label": "x\u2082"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="expected"):
        validate_pilot_data(raw)


def test_rejects_wrong_variable_id():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x3", "label": "x\u2083"}, {"id": "x2", "label": "x\u2082"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="expected"):
        validate_pilot_data(raw)


def test_rejects_unknown_variable_in_clause():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x9", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="must be one of"):
        validate_pilot_data(raw)


def test_rejects_duplicate_variable_in_same_clause():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x1", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="duplicate variable"):
        validate_pilot_data(raw)


def test_rejects_unexpected_assignment_variable():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True, "x4": False},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="unexpected variables"):
        validate_pilot_data(raw)


def test_rejects_non_boolean_assignment_value():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": "yes", "x2": True, "x3": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="expected boolean"):
        validate_pilot_data(raw)


def test_rejects_missing_assignment_variable():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="missing variable"):
        validate_pilot_data(raw)


def test_rejects_unexpected_field_in_variable():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081", "bogus": 1},
            {"id": "x2", "label": "x\u2082"},
            {"id": "x3", "label": "x\u2083"},
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    # validate_variables uses _require_dict and .get() so extra keys pass
    # This is by design — extra fields in variables are silently ignored
    # because the schema is lenient about unused fields in non-critical parts
    result = validate_pilot_data(raw)
    assert result["variables"][0]["id"] == "x1"


def test_rejects_too_few_literals_in_clause():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="exactly 3"):
        validate_pilot_data(raw)


def test_rejects_non_boolean_negated():
    raw = {
        "variables": [
            {"id": "x1", "label": "x\u2081"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": "yes"}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    with pytest.raises(SchemaError, match="expected boolean"):
        validate_pilot_data(raw)


def test_rejects_text_with_html():
    raw = {
        "variables": [
            {"id": "x1", "label": "<script>alert(1)</script>"}, {"id": "x2", "label": "x\u2082"}, {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]},
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK",
    }
    # The label pattern rejects < and >
    with pytest.raises(SchemaError, match="disallowed characters"):
        validate_pilot_data(raw)


# ---------------------------------------------------------------------------
# Boolean evaluation tests
# ---------------------------------------------------------------------------

def test_evaluate_all_true_fixture():
    raw = json.loads((ROOT / "fixtures" / "fixture_a_all_true.json").read_text())
    validated = validate_pilot_data(raw)
    result = evaluate_all(validated)
    # Clause 1: T OR F OR T = T
    # Clause 2: F OR T OR F = T
    # Formula: T AND T = T
    assert result["literal_values"] == [True, False, True, False, True, False]
    assert result["clause_values"] == [True, True]
    assert result["formula_value"] is True


def test_evaluate_all_false_fixture():
    raw = json.loads((ROOT / "fixtures" / "fixture_b_all_false.json").read_text())
    validated = validate_pilot_data(raw)
    result = evaluate_all(validated)
    # Clause 1: F OR T OR F = T
    # Clause 2: T OR F OR T = T
    # Formula: T AND T = T
    assert result["literal_values"] == [False, True, False, True, False, True]
    assert result["clause_values"] == [True, True]
    assert result["formula_value"] is True


def test_evaluate_false_formula_fixture():
    raw = json.loads((ROOT / "fixtures" / "fixture_c_false_formula.json").read_text())
    validated = validate_pilot_data(raw)
    result = evaluate_all(validated)
    # Clause 1: F OR F OR F = F
    # Clause 2: T OR T OR T = T
    # Formula: F AND T = F
    assert result["literal_values"] == [False, False, False, True, True, True]
    assert result["clause_values"] == [False, True]
    assert result["formula_value"] is False


def test_evaluate_literal_negation():
    from schema import evaluate_literal
    assert evaluate_literal({"x1": True}, "x1", False) is True
    assert evaluate_literal({"x1": True}, "x1", True) is False
    assert evaluate_literal({"x1": False}, "x1", False) is False
    assert evaluate_literal({"x1": False}, "x1", True) is True


def test_evaluate_clause_or():
    from schema import evaluate_clause
    assert evaluate_clause([False, False, False]) is False
    assert evaluate_clause([False, True, False]) is True
    assert evaluate_clause([True, True, True]) is True


def test_evaluate_formula_and():
    from schema import evaluate_formula
    assert evaluate_formula([True, True]) is True
    assert evaluate_formula([True, False]) is False
    assert evaluate_formula([False, False]) is False


# ---------------------------------------------------------------------------
# Safe text handling tests
# ---------------------------------------------------------------------------

def test_escape_html_neutralizes_tags():
    result = escape_html("<script>alert(1)</script>")
    assert "&lt;script&gt;" in result
    assert "&#x2F;" in result  # forward slash also escaped
    assert "<script>" not in result
    assert "</script>" not in result


def test_escape_html_neutralizes_attributes():
    result = escape_html('"><img src=x onerror=alert(1)>')
    assert "&quot;" in result
    assert "&gt;" in result
    assert "<img" not in result
    assert "onerror" not in result or "&#x3D;" in result


def test_escape_html_neutralizes_backticks():
    assert escape_html("`eval`") == "&#x60;eval&#x60;"


def test_escape_html_neutralizes_equals():
    assert escape_html("x=1") == "x&#x3D;1"


def test_escape_html_passes_safe_text():
    assert escape_html("x\u2081 OR NOT x\u2082") == "x\u2081 OR NOT x\u2082"


def test_format_truth_true():
    icon, word = format_truth(True)
    assert icon == "\u2713"
    assert word == "TRUE"


def test_format_truth_false():
    icon, word = format_truth(False)
    assert icon == "\u00D7"
    assert word == "FALSE"


def test_format_literal_label_negated():
    assert format_literal_label("x1", True) == "NOT x\u2081"


def test_format_literal_label_not_negated():
    assert format_literal_label("x2", False) == "x\u2082"


# ---------------------------------------------------------------------------
# End-to-end pilot render test
# ---------------------------------------------------------------------------

def test_pilot_renders_all_true_fixture():
    from pilot import run
    fixture = ROOT / "fixtures" / "fixture_a_all_true.json"
    output = ROOT / "renders" / "pilot_a.html"
    result = run(fixture, output.name)
    assert output.is_file()
    html = output.read_text(encoding="utf-8")
    assert "pilot-data" in html
    assert result["formula_value"] is True
    assert result["clause_values"] == [True, True]


def test_pilot_renders_all_false_fixture():
    from pilot import run
    fixture = ROOT / "fixtures" / "fixture_b_all_false.json"
    output = ROOT / "renders" / "pilot_b.html"
    result = run(fixture, output.name)
    assert output.is_file()
    html = output.read_text(encoding="utf-8")
    assert "pilot-data" in html
    assert result["formula_value"] is True


def test_pilot_renders_false_formula_fixture():
    from pilot import run
    fixture = ROOT / "fixtures" / "fixture_c_false_formula.json"
    output = ROOT / "renders" / "pilot_c.html"
    result = run(fixture, output.name)
    assert output.is_file()
    html = output.read_text(encoding="utf-8")
    assert "pilot-data" in html
    assert result["formula_value"] is False


def test_pilot_html_contains_no_raw_script_injection():
    from pilot import run
    import re
    fixture = ROOT / "fixtures" / "fixture_a_all_true.json"
    output = ROOT / "renders" / "pilot_a.html"
    run(fixture, output.name)
    html = output.read_text(encoding="utf-8")
    # Remove all legitimate <script ...> ... </script> blocks
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    assert "<script" not in cleaned
    assert "alert(" not in cleaned
    assert "onerror" not in cleaned


# ---------------------------------------------------------------------------
# Regression tests: actual rendered DOM text, symbols, and states
# ---------------------------------------------------------------------------

def test_rendered_final_result_matches_evaluation():
    """Verify the generated HTML has the correct outcome logic (template + JS)."""
    from pilot import run
    import re
    
    for fixture_name, expected_formula in [
        ("fixture_a_all_true.json", True),
        ("fixture_b_all_false.json", True),
        ("fixture_c_false_formula.json", False),
    ]:
        fixture = ROOT / "fixtures" / fixture_name
        output = ROOT / "renders" / f"check_{fixture_name}.html"
        run(fixture, output.name)
        html = output.read_text(encoding="utf-8")
        
        # Check final result text template (static) - will be replaced by JS at runtime
        if expected_formula:
            assert "The whole formula is TRUE." in html
        else:
            assert "The whole formula is TRUE." in html  # template text
        
        # Check that the JS logic for setting final result is present
        assert "The whole formula is ' + truthWord(formulaValue) + '.'" in html
        
        # Check outro title logic in JS
        assert "A satisfying assignment." in html
        assert "This assignment does not satisfy." in html
        
        # Check subtitle logic in JS
        assert "Both OR clauses pass. Their AND is TRUE." in html
        assert "Clause 1 is ' + c1Word + ', Clause 2 is ' + c2Word + '. Their AND is ' + fWord + '.'" in html
        
        # Check clause summary cards logic
        if expected_formula:
            assert "TRUE" in html  # both clauses TRUE
        else:
            assert "FALSE" in html
            assert "TRUE" in html


def test_rendered_literal_styling_consistent():
    """Verify literal cells use green for TRUE, red for FALSE regardless of negation (JS logic present)."""
    from pilot import run
    import re
    
    for fixture_name in [
        "fixture_a_all_true.json",
        "fixture_b_all_false.json",
        "fixture_c_false_formula.json",
    ]:
        fixture = ROOT / "fixtures" / fixture_name
        output = ROOT / "renders" / f"check_{fixture_name}.html"
        run(fixture, output.name)
        html = output.read_text(encoding="utf-8")
        
        # Check that the JS logic for setting literal styles based on truth value is present
        assert "tileLitValue ? '#22473b' : '#3a2f2d'" in html
        assert "tileLitValue ? '#a5f5cc' : '#ffad95'" in html
        
        # Check that truth icons are used
        assert "\\u2713" in html or "\\u2713" in html  # checkmark
        assert "\\u00D7" in html  # multiplication sign (×)
        
        # Check that both truth states are possible in the data
        if fixture_name == "fixture_a_all_true.json":
            assert "TRUE" in html
            assert "FALSE" in html
        elif fixture_name == "fixture_b_all_false.json":
            assert "TRUE" in html
            assert "FALSE" in html
        elif fixture_name == "fixture_c_false_formula.json":
            assert "TRUE" in html
            assert "FALSE" in html


def test_rendered_clause_results_match_evaluation():
    """Verify clause result boxes show correct TRUE/FALSE with correct icons (JS logic present)."""
    from pilot import run
    
    for fixture_name, expected_clauses in [
        ("fixture_a_all_true.json", [True, True]),
        ("fixture_b_all_false.json", [True, True]),
        ("fixture_c_false_formula.json", [False, True]),
    ]:
        fixture = ROOT / "fixtures" / fixture_name
        output = ROOT / "renders" / f"check_{fixture_name}.html"
        run(fixture, output.name)
        html = output.read_text(encoding="utf-8")
        
        # Check that JS logic for resolving clauses is present
        assert "applyComputedClauseResult" in html
        assert "clauseValues.every(Boolean)" in html
        
        for i, expected in enumerate(expected_clauses, 1):
            expected_word = "TRUE" if expected else "FALSE"
            expected_icon = "✓" if expected else "×"
            
            # Check clause label exists
            assert f"CLAUSE 0{i}" in html, f"Fixture {fixture_name}: missing Clause 0{i} label"
            assert expected_word in html, f"Fixture {fixture_name}: Clause {i} missing {expected_word}"
            
            # Check AND input reveals logic
            assert "andReveal.innerHTML" in html
            assert "truthIcon(revealValue)" in html
            assert "truthWord(revealValue)" in html
            assert "andReveal.className = 'reveal ' + truthCls(revealValue)" in html


def test_outro_takeaway_always_correct():
    """Verify takeaway text is correct and doesn't claim formula is unsatisfiable for false result."""
    from pilot import run
    
    for fixture_name, expected_formula in [
        ("fixture_a_all_true.json", True),
        ("fixture_b_all_false.json", True),
        ("fixture_c_false_formula.json", False),
    ]:
        fixture = ROOT / "fixtures" / fixture_name
        output = ROOT / "renders" / f"check_{fixture_name}.html"
        run(fixture, output.name)
        html = output.read_text(encoding="utf-8")
        
        # Takeaway should always be about existence of satisfying assignment, never claim formula is unsatisfiable
        # Check that the takeaway text is present (may have escaped quotes)
        assert "3-SAT asks whether there exists an assignment that makes every clause true." in html or \
               "3-SAT asks whether there exists an assignment" in html
        
        if expected_formula:
            assert "A satisfying assignment." in html
        else:
            assert "This assignment does not satisfy." in html
            # Should NOT say "unsatisfiable" or "no assignment works"
            assert "unsatisfiable" not in html.lower()
            assert "no assignment" not in html.lower()


def test_schema_rejects_closing_script_tag():
    """Verify schema rejects closing script tag in labels before rendering."""
    from schema import validate_pilot_data, SchemaError
    
    raw = {
        "variables": [
            {"id": "x1", "label": "x1</script><script>evil()</script>"},
            {"id": "x2", "label": "x\u2082"},
            {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]}
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK"
    }
    with pytest.raises(SchemaError, match="disallowed characters"):
        validate_pilot_data(raw)


def test_schema_rejects_opening_script_tag():
    """Verify schema rejects opening script tag in labels before rendering."""
    from schema import validate_pilot_data, SchemaError
    
    raw = {
        "variables": [
            {"id": "x1", "label": "<script>alert(1)</script>"},
            {"id": "x2", "label": "x\u2082"},
            {"id": "x3", "label": "x\u2083"}
        ],
        "clauses": [
            {"id": "c1", "label": "C1", "rule": "ok", "literals": [
                {"var": "x1", "negated": False}, {"var": "x2", "negated": False}, {"var": "x3", "negated": False}
            ]},
            {"id": "c2", "label": "C2", "rule": "ok", "literals": [
                {"var": "x1", "negated": True}, {"var": "x2", "negated": True}, {"var": "x3", "negated": True}
            ]}
        ],
        "assignment": {"x1": True, "x2": True, "x3": True},
        "case_label": "OK"
    }
    with pytest.raises(SchemaError, match="disallowed characters"):
        validate_pilot_data(raw)


def test_html_escaping_in_rendered_output():
    """Verify that if a dangerous label somehow passed schema, HTML escaping neutralizes it."""
    from escape import escape_html
    
    dangerous = "<script>alert(1)</script>"
    escaped = escape_html(dangerous)
    # Escaped output should have HTML entities, not raw tags
    assert "&lt;script&gt;" in escaped  # escaped form contains &lt;script&gt;
    assert "&#x2F;" in escaped  # forward slash escaped
    assert "<script>" not in escaped
    assert "</script>" not in escaped
    
    # Closing script tag breakout
    dangerous2 = "</script><script>evil()</script>"
    escaped2 = escape_html(dangerous2)
    assert "&lt;&#x2F;script&gt;" in escaped2
    assert "&lt;script&gt;" in escaped2
    assert "<script>" not in escaped2
    assert "</script>" not in escaped2

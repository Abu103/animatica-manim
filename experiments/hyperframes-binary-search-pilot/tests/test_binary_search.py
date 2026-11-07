"""Tests for the binary search HyperFrames pilot: schema validation,
binary search computation, safe text handling, and end-to-end rendering.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from binary_search import binary_search_steps, compute_result
from escape import escape_html, format_truth
from schema import SchemaError, validate_binary_search_data


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_validates_find_13_fixture():
    raw = json.loads((ROOT / "fixtures" / "fixture_find_13.json").read_text())
    result = validate_binary_search_data(raw)
    assert result["array"] == [1, 3, 5, 7, 9, 11, 13]
    assert result["target"] == 13
    assert result["case_label"] == "FIND 13 • SORTED ARRAY"


def test_rejects_extra_top_level_key():
    raw = {
        "array": [1, 3, 5],
        "target": 3,
        "case_label": "OK",
        "bogus": 1,
    }
    with pytest.raises(SchemaError, match="unexpected top-level keys"):
        validate_binary_search_data(raw)


def test_rejects_empty_array():
    raw = {"array": [], "target": 3, "case_label": "OK"}
    with pytest.raises(SchemaError, match="length must be 1"):
        validate_binary_search_data(raw)


def test_rejects_unsorted_array():
    raw = {"array": [3, 1, 5], "target": 3, "case_label": "OK"}
    with pytest.raises(SchemaError, match="strictly ascending"):
        validate_binary_search_data(raw)


def test_rejects_duplicate_array_value():
    raw = {"array": [1, 3, 3, 5], "target": 3, "case_label": "OK"}
    with pytest.raises(SchemaError, match="strictly ascending"):
        validate_binary_search_data(raw)


def test_rejects_non_integer_target():
    raw = {"array": [1, 3, 5], "target": "three", "case_label": "OK"}
    with pytest.raises(SchemaError, match="expected integer"):
        validate_binary_search_data(raw)


def test_rejects_boolean_target():
    raw = {"array": [1, 3, 5], "target": True, "case_label": "OK"}
    with pytest.raises(SchemaError, match="expected integer"):
        validate_binary_search_data(raw)


def test_rejects_text_with_html():
    raw = {
        "array": [1, 3, 5],
        "target": 3,
        "case_label": "<script>alert(1)</script>",
    }
    with pytest.raises(SchemaError, match="disallowed characters"):
        validate_binary_search_data(raw)


# ---------------------------------------------------------------------------
# Binary search computation tests
# ---------------------------------------------------------------------------

def test_binary_search_steps_find_13():
    """Verify actual computed steps for finding 13 in [1,3,5,7,9,11,13]."""
    steps = binary_search_steps([1, 3, 5, 7, 9, 11, 13], 13)
    assert len(steps) == 3

    # Step 1: range [0,6], mid=3, value=7, 13 > 7 → too low, eliminate [0,3]
    assert steps[0]["low"] == 0
    assert steps[0]["high"] == 6
    assert steps[0]["mid"] == 3
    assert steps[0]["mid_value"] == 7
    assert steps[0]["comparison"] == "too_low"
    assert steps[0]["eliminated"] == [0, 1, 2, 3]
    assert steps[0]["found_index"] is None

    # Step 2: range [4,6], mid=5, value=11, 13 > 11 → too low, eliminate [4,5]
    assert steps[1]["low"] == 4
    assert steps[1]["high"] == 6
    assert steps[1]["mid"] == 5
    assert steps[1]["mid_value"] == 11
    assert steps[1]["comparison"] == "too_low"
    assert steps[1]["eliminated"] == [4, 5]
    assert steps[1]["found_index"] is None

    # Step 3: range [6,6], mid=6, value=13 → found
    assert steps[2]["low"] == 6
    assert steps[2]["high"] == 6
    assert steps[2]["mid"] == 6
    assert steps[2]["mid_value"] == 13
    assert steps[2]["comparison"] == "found"
    assert steps[2]["eliminated"] == []
    assert steps[2]["found_index"] == 6


def test_binary_search_steps_found_first_element():
    steps = binary_search_steps([1, 3, 5, 7, 9, 11, 13], 1)
    assert steps[0]["mid"] == 3
    assert steps[0]["mid_value"] == 7
    assert steps[0]["comparison"] == "too_high"
    # Eventually finds at index 0
    last = steps[-1]
    assert last["comparison"] == "found"
    assert last["found_index"] == 0


def test_binary_search_steps_not_found():
    steps = binary_search_steps([1, 3, 5, 7, 9, 11, 13], 14)
    found = any(s["comparison"] == "found" for s in steps)
    assert found is False


def test_binary_search_steps_single_element_found():
    steps = binary_search_steps([42], 42)
    assert len(steps) == 1
    assert steps[0]["comparison"] == "found"
    assert steps[0]["found_index"] == 0


def test_binary_search_steps_single_element_not_found():
    steps = binary_search_steps([42], 99)
    assert len(steps) == 1
    # 99 > 42, so mid value 42 is "too low" for target 99
    assert steps[0]["comparison"] == "too_low"
    found = any(s["comparison"] == "found" for s in steps)
    assert found is False


def test_compute_result_find_13():
    result = compute_result([1, 3, 5, 7, 9, 11, 13], 13)
    assert result["found"] is True
    assert result["found_index"] == 6
    assert result["target"] == 13
    assert len(result["steps"]) == 3


def test_compute_result_not_found():
    result = compute_result([1, 3, 5, 7, 9, 11, 13], 14)
    assert result["found"] is False
    assert result["found_index"] == -1


# ---------------------------------------------------------------------------
# Safe text handling tests
# ---------------------------------------------------------------------------

def test_escape_html_neutralizes_tags():
    result = escape_html("<script>alert(1)</script>")
    assert "&lt;script&gt;" in result
    assert "&#x2F;" in result  # forward slash also escaped
    assert "<script>" not in result
    assert "</script>" not in result


def test_escape_html_passes_safe_text():
    assert escape_html("FIND 13") == "FIND 13"


def test_format_truth_true():
    icon, word = format_truth(True)
    assert icon == "\u2713"
    assert word == "TRUE"


def test_format_truth_false():
    icon, word = format_truth(False)
    assert icon == "\u00D7"
    assert word == "FALSE"


# ---------------------------------------------------------------------------
# End-to-end pilot render test
# ---------------------------------------------------------------------------

def test_pilot_renders_find_13_fixture():
    from binary_search_pilot import run
    fixture = ROOT / "fixtures" / "fixture_find_13.json"
    output = ROOT / "renders_found" / "binary_search_find_13.html"
    bs_data = run(fixture, output.name, output_dir=ROOT / "renders_found")
    assert output.is_file()
    html = output.read_text(encoding="utf-8")
    assert "search-data" in html
    assert bs_data["found"] is True
    assert bs_data["found_index"] == 6
    assert bs_data["target"] == 13
    assert len(bs_data["steps"]) == 3


def test_pilot_renders_not_found_fixture():
    from binary_search_pilot import run
    fixture = ROOT / "fixtures" / "fixture_not_found.json"
    output = ROOT / "renders_not_found" / "binary_search_not_found.html"
    bs_data = run(fixture, output.name, output_dir=ROOT / "renders_not_found")
    assert output.is_file()
    html = output.read_text(encoding="utf-8")
    assert "search-data" in html
    assert bs_data["found"] is False
    assert bs_data["found_index"] == -1
    assert bs_data["target"] == 8
    assert len(bs_data["steps"]) == 3
    # Verify the not-found result logic is present
    assert "Not found." in html
    assert "not in array" in html
    assert "data.found" in html


def test_pilot_html_contains_no_raw_script_injection():
    from binary_search_pilot import run
    fixture = ROOT / "fixtures" / "fixture_find_13.json"
    output = ROOT / "renders_found" / "binary_search_find_13.html"
    run(fixture, output.name, output_dir=ROOT / "renders_found")
    html = output.read_text(encoding="utf-8")
    # Remove all legitimate <script ...> ... </script> blocks
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    assert "<script" not in cleaned
    assert "alert(" not in cleaned
    assert "onerror" not in cleaned


def test_rendered_steps_match_computation():
    """Verify the generated HTML contains step logic derived from data."""
    from binary_search_pilot import run
    fixture = ROOT / "fixtures" / "fixture_find_13.json"
    output = ROOT / "renders_found" / "binary_search_find_13.html"
    bs_data = run(fixture, output.name, output_dir=ROOT / "renders_found")
    html = output.read_text(encoding="utf-8")

    # The template generates step text dynamically from data.steps
    # Verify the JS logic that builds step text is present
    assert "stepTexts" in html
    assert "step.mid_value" in html
    assert "step.low" in html
    assert "step.high" in html
    assert "step.comparison" in html

    # Verify the injected JSON contains the correct steps
    import json as json_mod
    data_match = re.search(r'<script type="application/json" id="search-data">(.*?)</script>', html, re.DOTALL)
    assert data_match is not None
    injected = json_mod.loads(data_match.group(1))
    assert len(injected["steps"]) == len(bs_data["steps"])
    for i, step in enumerate(injected["steps"]):
        assert step["mid"] == bs_data["steps"][i]["mid"]
        assert step["mid_value"] == bs_data["steps"][i]["mid_value"]
        assert step["comparison"] == bs_data["steps"][i]["comparison"]

    # Check found result is present in JS logic
    assert "Found at index" in html
    assert "data.found_index" in html


def test_rendered_takeaway_honest():
    """Verify takeaway doesn't imply every search finds the target."""
    from binary_search_pilot import run
    fixture = ROOT / "fixtures" / "fixture_find_13.json"
    output = ROOT / "renders_found" / "binary_search_find_13.html"
    run(fixture, output.name, output_dir=ROOT / "renders_found")
    html = output.read_text(encoding="utf-8")
    assert "Binary search repeatedly halves a sorted search range." in html
    assert "Not every search finds the target." in html

"""extract_json: strings that hold brackets, and output that is one closer short."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from animatica.ai.base import extract_json

FIXTURES = Path(__file__).parent / "fixtures" / "eval_replay"


def test_closing_brace_inside_a_string_does_not_end_the_object():
    assert extract_json('x {"code": "if (a) { b }", "n": 1} tail') == {"code": "if (a) { b }", "n": 1}


def test_escaped_quote_inside_a_string_is_not_the_end_of_it():
    assert extract_json(r'{"s": "say \"}\" now", "n": 2}') == {"s": 'say "}" now', "n": 2}


def test_one_missing_closing_brace_is_added():
    assert extract_json('{"a": {"b": [1, 2]}') == {"a": {"b": [1, 2]}}


def test_several_missing_closers_are_added_in_order():
    assert extract_json('{"a": [{"b": 1}, {"c": [2') == {"a": [{"b": 1}, {"c": [2]}]}


def test_missing_closer_inside_a_fence_is_added():
    assert extract_json('```json\n{"a": [1, 2]\n```') == {"a": [1, 2]}


def test_output_cut_inside_a_string_is_an_error_that_says_so():
    with pytest.raises(ValueError, match="cut off"):
        extract_json('{"a": "half a sent')


def test_cut_off_after_a_key_is_an_error_not_a_guess():
    with pytest.raises((ValueError, json.JSONDecodeError)):
        extract_json('{"a": 1, "b":')


def test_mismatched_closers_are_not_repaired():
    with pytest.raises((ValueError, json.JSONDecodeError)):
        extract_json('{"a": [1, 2}')


def test_recorded_quadratic_formula_output_missing_its_last_brace():
    """Real NIM output that ended `...}]}]` with the final `}` missing: it used to fail."""
    rec = json.loads((FIXTURES / "19-derive-the-quadratic-formula-step-by-ste.json").read_text(encoding="utf-8"))
    assert not rec["response"].rstrip().endswith("}}")
    sb = extract_json(rec["response"])
    assert sb["scenes"][0]["beats"][0]["component"] == "formula_derivation"

import json

import pytest
from pydantic import ValidationError

from animatica.components.code_diff import CodeDiff

BEFORE = "def area(r):\n    return 3.14 * r * r\n"
AFTER = "import math\n\ndef area(r):\n    return math.pi * r * r\n"


def params(**kw):
    return CodeDiff.Params.model_validate({"title": "Use math.pi", "before": BEFORE, "after": AFTER, **kw})


def test_diff_rows_mark_kept_removed_and_added_lines():
    assert CodeDiff.diff_rows(BEFORE, AFTER) == [
        ("add", "import math"),
        ("add", ""),
        ("keep", "def area(r):"),
        ("remove", "    return 3.14 * r * r"),
        ("add", "    return math.pi * r * r"),
    ]


def test_a_replaced_block_shows_removals_before_additions():
    rows = CodeDiff.diff_rows("a\nb\nc", "a\nX\nY\nc")
    assert rows == [("keep", "a"), ("remove", "b"), ("add", "X"), ("add", "Y"), ("keep", "c")]


def test_trailing_newline_and_crlf_do_not_create_changes():
    assert CodeDiff.diff_rows("a\nb\n", "a\r\nb") == [("keep", "a"), ("keep", "b")]


def test_duration_is_two_and_a_half_seconds_plus_half_a_second_per_changed_line():
    assert CodeDiff().duration(params()) == pytest.approx(2.5 + 0.5 * 4)


def test_identical_code_is_rejected():
    with pytest.raises(ValidationError, match="no difference"):
        params(after=BEFORE)


def test_double_escaped_newlines_from_a_model_are_repaired():
    p = CodeDiff.Params.model_validate({"title": "t", "before": "x = 1\\ny = 2", "after": "x = 1\\ny = 3"})
    assert p.before.count("\n") == 1 and p.after.endswith("y = 3")


def test_too_many_lines_or_too_long_a_line_is_rejected():
    with pytest.raises(ValidationError, match="lines"):
        params(before="\n".join(f"a{i}" for i in range(13)), after="b")
    with pytest.raises(ValidationError, match="characters"):
        params(after="x" * 49)


def test_empty_before_or_after_is_allowed_for_pure_additions():
    p = CodeDiff.Params.model_validate({"title": "t", "before": "", "after": "print('hi')"})
    assert CodeDiff.diff_rows(p.before, p.after) == [("add", "print('hi')")]


def test_fallback_text_is_a_plain_unified_diff():
    text = CodeDiff().fallback_text(params())
    assert text.splitlines()[0] == "Use math.pi"
    assert "+import math" in text and "-    return 3.14 * r * r" in text and "\n def area(r):" in text


def test_schema_is_json_serialisable():
    json.dumps(CodeDiff.Params.model_json_schema())


def test_blank_lines_are_valid_rows_in_every_position():
    rows = CodeDiff.diff_rows("a\n\nb", "a\n\nc")
    assert ("keep", "") in rows and rows[-2:] == [("remove", "b"), ("add", "c")]


def test_indent_is_measured_in_columns_with_tabs_expanded_to_four():
    assert CodeDiff.indent("    return x") == (4, "return x")
    assert CodeDiff.indent("\treturn x") == (4, "return x")
    assert CodeDiff.indent("  \tx") == (4, "x")  # a tab goes to the next multiple of four
    assert CodeDiff.indent("x") == (0, "x")
    assert CodeDiff.indent("") == (0, "")
    assert CodeDiff.indent("    ") == (0, "")  # a whitespace-only line is blank

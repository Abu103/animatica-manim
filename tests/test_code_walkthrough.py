import pytest

from animatica.components.code_walkthrough import CodeWalkthrough
from animatica.components.registry import default_registry


def test_registered():
    assert "code_walkthrough" in default_registry().names()


def test_duration_is_3s_plus_1s_per_line():
    p = CodeWalkthrough.Params(title="t", code="a = 1\nb = 2", lines=[1, 2])
    assert CodeWalkthrough().duration(p) == pytest.approx(3.0 + 1.0 * 2)


def test_duration_defaults_to_all_lines():
    p = CodeWalkthrough.Params(title="t", code="a = 1\nb = 2\nc = 3")
    assert CodeWalkthrough().duration(p) == pytest.approx(3.0 + 1.0 * 3)


def test_rejects_too_long_code():
    with pytest.raises(Exception):
        CodeWalkthrough.Params(title="t", code="x" * 301)


def test_fallback_text_contains_code_and_variables():
    p = CodeWalkthrough.Params(
        title="Walk",
        code="x = 1\ny = x + 1",
        lines=[1, 2],
        variables={"x": "1", "y": "2"},
    )
    text = CodeWalkthrough().fallback_text(p)
    assert "Walk" in text
    assert "x = 1" in text
    assert "y = x + 1" in text
    assert "x = 1" in text
    assert "y = 2" in text


def test_empty_lines_defaults_to_all():
    p = CodeWalkthrough.Params(title="t", code="a = 1\nb = 2", lines=[])
    assert CodeWalkthrough().duration(p) == pytest.approx(3.0 + 1.0 * 2)

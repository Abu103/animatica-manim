import pytest

from animatica.components.stat_callout import StatCallout
from animatica.components.registry import default_registry


def test_registered():
    assert "stat_callout" in default_registry().names()


def test_duration_is_3s_fixed():
    p = StatCallout.Params(value="98%", label="pass rate")
    assert StatCallout().duration(p) == 3.0


def test_rejects_too_long_value():
    with pytest.raises(Exception):
        StatCallout.Params(value="x" * 301, label="label")


def test_rejects_too_long_label():
    with pytest.raises(Exception):
        StatCallout.Params(value="98%", label="x" * 301)


def test_fallback_text_contains_value_and_label():
    p = StatCallout.Params(value="98%", label="pass rate", delta="+12% vs last year")
    text = StatCallout().fallback_text(p)
    assert "98%" in text and "pass rate" in text and "+12% vs last year" in text


def test_fallback_text_without_delta():
    p = StatCallout.Params(value="42", label="answer")
    text = StatCallout().fallback_text(p)
    assert "42" in text and "answer" in text and "(" not in text

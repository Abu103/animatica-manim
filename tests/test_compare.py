import pytest

from animatica.components.compare import Compare
from animatica.components.registry import default_registry


def test_registered():
    assert "compare" in default_registry().names()


def test_duration_scales_with_bullets():
    side = {"heading": "A", "bullets": ["x", "y", "z"]}
    p = Compare.Params(title="t", left=side, right={"heading": "B", "bullets": ["p", "q"]})
    assert Compare().duration(p) == pytest.approx(2.0 + 0.6 * 5)


@pytest.mark.parametrize("bad", [
    {"title": "t", "left": {"heading": "A", "bullets": []}, "right": {"heading": "B", "bullets": ["x"]}},
    {"title": "t", "left": {"heading": "A", "bullets": ["x"] * 7}, "right": {"heading": "B", "bullets": ["y"]}},
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        Compare.Params(**bad)


def test_fallback_text_has_both_headings():
    p = Compare.Params(title="t", left={"heading": "Cats", "bullets": ["meow"]}, right={"heading": "Dogs", "bullets": ["bark"]})
    t = Compare().fallback_text(p)
    assert "Cats" in t and "Dogs" in t

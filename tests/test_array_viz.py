import pytest

from animatica.components.array_viz import ArrayViz
from animatica.components.registry import default_registry


def test_registered():
    assert "array_viz" in default_registry().names()


def test_duration_is_2s_plus_0_8_per_step():
    p = ArrayViz.Params(title="t", values=[3, 1, 2], steps=[{"highlight": [0]}, {"swap": [0, 2]}])
    assert ArrayViz().duration(p) == pytest.approx(2.0 + 0.8 * 2)


@pytest.mark.parametrize("bad", [
    {"title": "t", "values": [1]},                                   # need 2+
    {"title": "t", "values": list(range(13))},                       # max 12
    {"title": "t", "values": [1, 2], "steps": [{"swap": [0, 5]}]},   # index out of range
    {"title": "t", "values": [1, 2], "steps": [{"highlight": [9]}]}, # index out of range
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        ArrayViz.Params(**bad)


def test_fallback_text():
    p = ArrayViz.Params(title="Sort demo", values=[3, 1, 2])
    assert "3" in ArrayViz().fallback_text(p)

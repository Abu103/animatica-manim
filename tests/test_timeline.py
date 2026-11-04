import pytest

from animatica.components.registry import default_registry
from animatica.components.timeline import Timeline


def test_registered():
    assert "timeline" in default_registry().names()


def test_duration_is_2s_plus_0_8_per_event():
    p = Timeline.Params(title="t", events=[{"label": "a", "text": "x"}, {"label": "b", "text": "y"}])
    assert Timeline().duration(p) == pytest.approx(2.0 + 0.8 * 2)


@pytest.mark.parametrize("bad", [
    {"title": "t", "events": []},
    {"title": "t", "events": [{"label": f"e{i}", "text": "x"} for i in range(9)]},
    {"title": "t", "events": [{"text": "no label"}]},
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        Timeline.Params(**bad)


def test_fallback_text():
    p = Timeline.Params(title="History", events=[{"label": "1969", "text": "Moon landing"}])
    assert "1969" in Timeline().fallback_text(p)

import pytest

from animatica.components.registry import default_registry
from animatica.components.timeline import Timeline
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
)


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


# ---------------------------------------------------------------------------
# B4: the timeline has to fit the frame, keep its text apart and fit its clock
# ---------------------------------------------------------------------------


def _conformance_params() -> Timeline.Params:
    """The parameters of the conformance storyboard, tests/conformance/timeline.json."""
    return Timeline.Params(
        title="History",
        events=[
            {"label": "1969", "text": "Moon landing"},
            {"label": "1989", "text": "Web invented"},
        ],
    )


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_timeline_content_stays_inside_the_safe_area(width, height):
    """No part of the timeline may reach into the safe-area margin."""
    beat = play_component(Timeline(), _conformance_params(), width, height)

    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_timeline_text_does_not_overlap(width, height):
    """The labels and their descriptions must not land on each other."""
    beat = play_component(Timeline(), _conformance_params(), width, height)

    assert_no_text_overlap(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_timeline_beat_fits_its_declared_duration(width, height):
    """The animations must fit inside the duration the component declared.

    Every event used to be faded in one mobject at a time, so a beat of
    3.6s ran for 5.6s and the captions drifted out of sync.
    """
    beat = play_component(Timeline(), _conformance_params(), width, height)

    assert_beat_timing(beat)

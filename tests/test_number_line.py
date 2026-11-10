import pytest

from animatica.components.number_line import NumberLine
from animatica.components.registry import default_registry
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
)


def test_registered():
    assert "number_line" in default_registry().names()


def test_duration_is_2s_plus_0_7_per_jump():
    p = NumberLine.Params(title="t", start=0, end=10, jumps=[(0, 3), (3, 7)])
    assert NumberLine().duration(p) == pytest.approx(2.0 + 0.7 * 2)


@pytest.mark.parametrize("bad", [
    {"title": "t", "start": 10, "end": 0},                    # end <= start
    {"title": "t", "start": 0, "end": 10, "marks": [11]},      # mark out of range
    {"title": "t", "start": 0, "end": 10, "jumps": [(-1, 5)]}, # jump out of range
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        NumberLine.Params(**bad)


def test_fallback_text_mentions_jumps():
    p = NumberLine.Params(title="Demo", start=0, end=10, jumps=[(0, 5)])
    assert "0 -> 5" in NumberLine().fallback_text(p)


# ---------------------------------------------------------------------------
# B4: the number line has to fit the frame, keep its text apart and fit its clock
# ---------------------------------------------------------------------------


def _number_line_params() -> NumberLine.Params:
    """The parameters of the conformance storyboard, tests/conformance/number_line.json."""
    return NumberLine.Params(
        title="Demo line", start=0, end=10, marks=[5], jumps=[(0, 3), (3, 7)]
    )


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_number_line_content_stays_inside_the_safe_area(width, height):
    """No part of the number line may reach into the safe-area margin.

    The line and its labels were scaled up to fill the frame, which pushed
    the end labels past the margin frame-lint keeps free.
    """
    beat = play_component(NumberLine(), _number_line_params(), width, height)

    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_number_line_text_does_not_overlap(width, height):
    """The title, the tick labels and the jump labels must not collide."""
    beat = play_component(NumberLine(), _number_line_params(), width, height)

    assert_no_text_overlap(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_number_line_beat_fits_its_declared_duration(width, height):
    """The animations must fit inside the duration the component declared."""
    beat = play_component(NumberLine(), _number_line_params(), width, height)

    assert_beat_timing(beat)

import pytest

from animatica.components.array_viz import ArrayViz, opacity_for, swap_targets
from animatica.components.registry import default_registry
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
)


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


def test_swap_targets_reads_original_centers():
    c = [(-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
    assert swap_targets(c, 0, 2) == [(0, (1.0, 0.0, 0.0)), (2, (-1.0, 0.0, 0.0))]


def test_swap_same_index_is_noop():
    assert swap_targets([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], 1, 1) == []


def test_swap_with_duplicate_values_uses_indices():
    c = [(-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
    assert [ix for ix, _ in swap_targets(c, 0, 1)] == [0, 1]


@pytest.mark.render
def test_swap_lands_boxes_on_original_centers(run_component, monkeypatch):
    """F1: values [5, 9, 1], swap [0, 2] — boxes land on each other's ORIGINAL centers (never both at x=1.14)."""
    import animatica.components.array_viz as av_mod

    p = ArrayViz.Params(title="t", values=[5, 9, 1], steps=[{"swap": [0, 2]}])
    captured: list[tuple[float, tuple]] = []
    orig_play = av_mod.Clock.play

    def spy(self, *anims, run_time):
        captured.append((run_time, anims))
        return orig_play(self, *anims, run_time=run_time)

    monkeypatch.setattr(av_mod.Clock, "play", spy)
    scene, warnings = run_component(ArrayViz(), p)

    swap_plays = [c for c in captured if c[0] == 0.8 and len(c[1]) == 2]
    assert len(swap_plays) == 1, captured
    _, anims = swap_plays[0]
    landed = {}
    for anim in anims:
        builder = anim.build() if hasattr(anim, "build") else anim
        box = builder.mobject
        landed[box.text] = box.target.get_center()[0]
    assert set(landed) == {"5", "1"}, landed
    assert landed["5"] > landed["1"], landed  # "5" (index 0) took index 2's right slot
    assert landed["5"] - landed["1"] > 0.5, landed  # two distinct slots, not the collapsed 1.14 of the bug


def test_opacity_inside_range_is_full():
    assert opacity_for(3, 2, 5) == 1.0


def test_opacity_outside_range_is_dimmed():
    assert opacity_for(0, 2, 5) == 0.25
    assert opacity_for(6, 2, 5) == 0.25


def test_opacity_without_range_is_full():
    assert opacity_for(0, None, None) == 1.0


# ---------------------------------------------------------------------------
# B4: the array viz has to fit the frame, keep its text apart and fit its clock
# ---------------------------------------------------------------------------


def _array_params() -> ArrayViz.Params:
    """The parameters of the conformance storyboard, tests/conformance/array_viz.json."""
    return ArrayViz.Params(
        title="Bubble sort step",
        values=[3, 1, 2],
        steps=[{"highlight": [0, 1]}, {"swap": [0, 1]}],
    )


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_array_viz_content_stays_inside_the_safe_area(width, height):
    """No part of the array may reach into the safe-area margin.

    The whole array was scaled up to fill the frame, which stretched the
    title over the edges of the frame and into the margin.
    """
    beat = play_component(ArrayViz(), _array_params(), width, height)

    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_array_viz_text_does_not_overlap(width, height):
    """The values must not land on each other."""
    beat = play_component(ArrayViz(), _array_params(), width, height)

    assert_no_text_overlap(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_array_viz_beat_fits_its_declared_duration(width, height):
    """The animations must fit inside the duration the component declared."""
    beat = play_component(ArrayViz(), _array_params(), width, height)

    assert_beat_timing(beat)


# ---------------------------------------------------------------------------
# B4b: the value boxes fill the stage
# ---------------------------------------------------------------------------


def _array_title(beat):
    """The array viz's title."""
    from manim import Text

    titles = [m for m in beat.mobjects if isinstance(m, Text)]
    assert titles, "the array viz did not animate a title"
    return titles[0]


def _array_boxes(beat):
    """The array viz's row of value boxes."""
    from manim import VGroup

    groups = [m for m in beat.mobjects if isinstance(m, VGroup)]
    assert groups, "the array viz did not animate a group of boxes"
    return groups[0]


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_array_viz_boxes_fill_the_stage(width, height):
    """The value boxes must fill a good part of the frame.

    They were left at their natural size, so a three-element array was a
    small patch in the middle of an empty frame. The cap keeps them inside
    the safe area: at most 70% of the frame width.
    """
    beat = play_component(ArrayViz(), _array_params(), width, height)
    boxes = _array_boxes(beat)
    share = boxes.width / beat.frame_width

    assert share >= 0.4, (
        f"the value boxes fill {share:.1%} of the frame, they should fill "
        "at least 40%"
    )
    assert share <= 0.7 + 1e-6, (
        f"the value boxes fill {share:.1%} of the frame, they should fill "
        "at most 70%"
    )


# ---------------------------------------------------------------------------
# B4e: the title is at the top of the frame, centred, above the boxes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_array_viz_title_is_centred_above_the_boxes(width, height):
    """The title sits at the top of the frame, centred, above the boxes.

    It used to keep the place the layout gave it, which left it in the
    middle of the frame with the boxes hanging below it and the whole top
    of the frame empty.
    """
    beat = play_component(ArrayViz(), _array_params(), width, height)
    title = _array_title(beat)
    boxes = _array_boxes(beat)
    half_height = beat.frame_height / 2

    assert title.get_center()[0] == pytest.approx(0.0, abs=1e-3), (
        f"the title is centred at x={title.get_center()[0]:.3f}, it should be "
        "centred in the frame"
    )
    assert title.get_top()[1] == pytest.approx(half_height - 0.6, abs=1e-3), (
        f"the title's top is at y={title.get_top()[1]:.3f}, it should sit "
        f"{0.6:.1f} below the top edge (y={half_height - 0.6:.3f})"
    )
    assert title.get_bottom()[1] > boxes.get_top()[1], (
        f"the title's bottom is at y={title.get_bottom()[1]:.3f} and the "
        f"boxes' top at y={boxes.get_top()[1]:.3f}: the title must be above "
        "the boxes"
    )
    assert_inside_safe_area(beat)
    assert_no_text_overlap(beat)

import pytest

from animatica.components.bounce_sequence import BounceSequence, parabola_point, sum_rule_holds
from animatica.components.registry import default_registry
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
)

FIB = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55]


def test_registered():
    assert "bounce_sequence" in default_registry().names()


def test_duration_is_2s_plus_0_8_per_term():
    assert BounceSequence().duration(BounceSequence.Params(title="t", values=FIB)) == pytest.approx(2.0 + 0.8 * 11)


@pytest.mark.parametrize("bad", [
    {"title": "t", "values": [1]},                      # needs 2+ terms
    {"title": "t", "values": list(range(21))},          # max 20
    {"title": "t", "values": [1, -2]},                  # negative
    {"title": "t", "values": [1, float("inf")]},
    {"title": "t", "values": [1, 2], "labels": ["a"]},  # labels length mismatch
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        BounceSequence.Params(**bad)


def test_sum_rule_detects_fibonacci_but_not_other_sequences():
    assert [i for i in range(len(FIB)) if sum_rule_holds(FIB, i)] == list(range(2, 11))
    assert not any(sum_rule_holds([1, 2, 4, 8, 16], i) for i in range(5))


def test_parabola_hits_endpoints_and_bulges_up():
    a, b = (0.0, 0.0), (2.0, 1.0)
    assert parabola_point(a, b, 0.0, 1.0) == pytest.approx(a)
    assert parabola_point(a, b, 1.0, 1.0) == pytest.approx(b)
    mid = parabola_point(a, b, 0.5, 1.0)
    assert mid[1] > 0.5  # above the straight line (y = 0.5 at the midpoint)


def test_fallback_text_lists_values():
    t = BounceSequence().fallback_text(BounceSequence.Params(title="Fib", values=[0, 1, 1]))
    assert "Fib" in t and "0, 1, 1" in t


@pytest.mark.render
def test_plays_without_warnings_or_timing_overrun(run_component):
    s, warnings = run_component(BounceSequence(), BounceSequence.Params(title="Fibonacci", values=FIB))
    assert warnings == []
    assert s.renderer.num_plays >= 12


@pytest.mark.render
def test_two_terms_still_works(run_component):
    s, warnings = run_component(BounceSequence(), BounceSequence.Params(title="Tiny", values=[3, 7]))
    assert warnings == []


# ---------------------------------------------------------------------------
# B4: the bounce sequence has to fit the frame, keep its text apart and fit its clock
# ---------------------------------------------------------------------------


def _bounce_params() -> BounceSequence.Params:
    """The parameters of the conformance storyboard, tests/conformance/bounce_sequence.json."""
    return BounceSequence.Params(title="Fibonacci", values=[0, 1, 1, 2, 3])


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_bounce_sequence_content_stays_inside_the_safe_area(width, height):
    """No part of the sequence may reach into the safe-area margin.

    The title was scaled up to fill the frame, which pushed it over the top
    edge of the frame and into the margin frame-lint keeps free.
    """
    beat = play_component(BounceSequence(), _bounce_params(), width, height)

    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_bounce_sequence_text_does_not_overlap(width, height):
    """The title and the running sum must not land on each other."""
    beat = play_component(BounceSequence(), _bounce_params(), width, height)

    assert_no_text_overlap(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_bounce_sequence_beat_fits_its_declared_duration(width, height):
    """The animations must fit inside the duration the component declared."""
    beat = play_component(BounceSequence(), _bounce_params(), width, height)

    assert_beat_timing(beat)

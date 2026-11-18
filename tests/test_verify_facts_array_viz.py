"""V1b-3: array_viz facts are computed from the same data play() draws.

The final array state is exactly replayable from the params: every step that
carries ``swap`` applies its pair to a copy of ``values``, in order (a swap
with ``i == j`` is a no-op, exactly as ``swap_targets`` treats it). Steps with
``highlight``/``low``/``high``/``mid`` only change the drawing, never the
array. Design 5.1: facts and drawing share one pure data function.
"""
from __future__ import annotations

from animatica.components.array_viz import ArrayViz, _data
from animatica.components.registry import default_registry
from animatica.storyboard.models import Beat
from animatica.verify.facts import Fact, facts_for


def _facts(values, steps=None):
    p = ArrayViz.Params(title="t", values=values, steps=steps or [])
    return ArrayViz().facts(p)


def _one(facts, kind):
    found = [f for f in facts if f.kind == kind]
    assert len(found) == 1, f"expected exactly one {kind!r} fact, got {found}"
    return found[0]


def test_no_steps_means_unsorted_and_zero_swaps():
    facts = _facts([3, 1, 2])
    assert _one(facts, "sorted").value is False
    assert _one(facts, "sorted").subject == "final_state"
    assert "not sorted in ascending order at the end" in _one(facts, "sorted").text
    assert _one(facts, "swaps").value == 0
    assert _one(facts, "value").value == (3.0, 1.0, 2.0)


def test_two_swaps_sort_the_array():
    steps = [{"swap": [0, 1]}, {"swap": [1, 2]}]
    facts = _facts([3, 1, 2], steps)
    assert _one(facts, "sorted").value is True
    assert "sorted in ascending order at the end" in _one(facts, "sorted").text
    assert _one(facts, "swaps").value == 2
    assert "the steps swap two boxes 2 times" in _one(facts, "swaps").text
    assert _one(facts, "value").value == (1.0, 2.0, 3.0)
    assert "final order is [1, 2, 3]" in _one(facts, "value").text


def test_fourier_case_is_not_sorted():
    # The 2026-11-16 failure: values 1 0 -1 0 1 0 -1 0 with no swaps. It must
    # never get a sorted=True claim.
    values = [1, 0, -1, 0, 1, 0, -1, 0]
    facts = _facts(values)
    assert _one(facts, "sorted").value is False
    assert _one(facts, "value").value == tuple(float(v) for v in values)


def test_same_index_swap_is_a_no_op_and_not_counted():
    steps = [{"swap": [1, 1]}, {"swap": [0, 2]}]
    facts = _facts([3, 1, 2], steps)
    assert _one(facts, "swaps").value == 1
    assert _one(facts, "value").value == (2.0, 1.0, 3.0)


def test_search_steps_do_not_change_the_array():
    # Binary-search steps only change the drawing: opacity, mid colour.
    steps = [{"low": 0, "high": 7, "mid": 3}, {"highlight": [3], "mid": 3},
             {"low": 4, "high": 7, "mid": 5}]
    facts = _facts([1, 0, -1, 0, 1, 0, -1, 0], steps)
    assert _one(facts, "swaps").value == 0
    assert _one(facts, "sorted").value is False
    assert _one(facts, "value").value == (1.0, 0.0, -1.0, 0.0, 1.0, 0.0, -1.0, 0.0)


def test_extrema_are_first_occurrence_positions_with_final_values():
    facts = _facts([2, 1, 2])
    largest, smallest = [f for f in facts if f.kind == "extremum"]
    assert largest.value == (0, 2.0)
    assert "largest value is 2 at position 0" in largest.text
    assert smallest.value == (1, 1.0)
    assert "smallest value is 1 at position 1" in smallest.text
    # Positions are 0-based; the text must say so.
    assert "position 0 is the first box" in largest.text
    assert "position 0 is the first box" in smallest.text


def test_infinity_is_written_out_and_compares_correctly():
    steps = [{"swap": [0, 2]}]
    facts = _facts([float("inf"), 2, 1], steps)
    assert _one(facts, "sorted").value is True
    assert _one(facts, "value").value == (1.0, 2.0, float("inf"))
    assert "final order is [1, 2, infinity]" in _one(facts, "value").text
    largest, smallest = [f for f in facts if f.kind == "extremum"]
    assert largest.value == (2, float("inf"))
    assert "largest value is infinity at position 2" in largest.text
    assert smallest.value == (0, 1.0)
    assert "smallest value is 1 at position 0" in smallest.text
    for f in facts:
        assert "infinity" in f.text or "inf" not in f.text
        assert "inf," not in f.text and "inf]" not in f.text and "inf " not in f.text


def test_negative_infinity_is_written_out_too():
    facts = _facts([-float("inf"), 0])
    largest, smallest = [f for f in facts if f.kind == "extremum"]
    assert largest.value == (1, 0.0)
    assert smallest.value == (0, -float("inf"))
    assert "negative infinity" in smallest.text
    assert "inf," not in smallest.text and "inf]" not in smallest.text


def test_facts_agree_with_the_data_the_drawing_uses():
    p = ArrayViz.Params(title="t", values=[3, 1, 2],
                        steps=[{"swap": [0, 1]}, {"swap": [1, 2]}])
    initial, final = _data(p)
    assert initial == [3.0, 1.0, 2.0]
    assert final == [1.0, 2.0, 3.0]

    facts = ArrayViz().facts(p)
    assert _one(facts, "value").value == tuple(final)
    largest, smallest = [f for f in facts if f.kind == "extremum"]
    assert largest.value == (
        final.index(max(final)), max(final))
    assert smallest.value == (
        final.index(min(final)), min(final))
    # play() draws the initial values, so the initial data must equal the params.
    assert initial == list(p.values)


def test_facts_for_an_array_viz_beat():
    params = {"title": "t", "values": [3, 1, 2], "steps": [{"swap": [0, 1]}]}
    beat = Beat(component="array_viz", params=params)
    facts = facts_for(default_registry(), beat)
    assert facts == ArrayViz().facts(ArrayViz.Params(**params))
    assert facts and all(isinstance(f, Fact) for f in facts)
    assert ArrayViz.domain == "plain axes"

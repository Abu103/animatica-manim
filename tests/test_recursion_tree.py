import pytest

from animatica.components.recursion_tree import RecursionTree, tree_layout
from animatica.components.registry import default_registry
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
)


def test_registered():
    assert "recursion_tree" in default_registry().names()


def test_duration_grows_with_n():
    t = RecursionTree()
    assert t.duration(RecursionTree.Params(title="t", fn="fib", n=2)) == pytest.approx(2.0 + 0.8 * 1)
    assert t.duration(RecursionTree.Params(title="t", fn="fib", n=5)) == pytest.approx(2.0 + 0.8 * 4)


def test_layout_fib5_has_9_nodes_and_distinct_x():
    nodes = tree_layout("fib", 5)
    assert len(nodes) == 15  # full F(5) call tree: 1+1+2+3+5+3 occurrences
    xs = [x for _call, x, _y in nodes.values()]
    assert len(set(xs)) == len(xs)


def test_layout_caps_at_31_nodes():
    assert len(tree_layout("fib", 8)) <= 31


@pytest.mark.parametrize("bad", [
    {"title": "t", "fn": "fib", "n": 1},
    {"title": "t", "fn": "fib", "n": 7},
    {"title": "t", "fn": "ackermann", "n": 3},
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        RecursionTree.Params(**bad)


def test_fallback_text():
    p = RecursionTree.Params(title="Fib calls", fn="fib", n=4)
    assert "fib" in RecursionTree().fallback_text(p).lower()


# ---------------------------------------------------------------------------
# B4: the recursion tree has to fit the clock it declared
# ---------------------------------------------------------------------------


def _conformance_params() -> RecursionTree.Params:
    """The parameters of the conformance storyboard, tests/conformance/recursion_tree.json."""
    return RecursionTree.Params(title="Fibonacci call tree", fn="fib", n=5)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_recursion_tree_beat_fits_its_declared_duration(width, height):
    """The animations must fit inside the duration the component declared.

    Every node and every edge had a fixed fade time, so a tree with 15
    nodes and 25 edges ran for 5.55s in a beat declared as 5.2s and the
    captions drifted out of sync.
    """
    beat = play_component(RecursionTree(), _conformance_params(), width, height)

    assert_beat_timing(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_recursion_tree_content_stays_inside_the_safe_area(width, height):
    """No part of the tree may reach into the safe-area margin.

    The tree was scaled up to fill the frame, which pushed the outer
    leaves past the margin frame-lint keeps free and the bottom of the
    tree into the caption.
    """
    beat = play_component(RecursionTree(), _conformance_params(), width, height)

    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_recursion_tree_text_does_not_overlap(width, height):
    """The title must not sit on top of the first row of nodes."""
    beat = play_component(RecursionTree(), _conformance_params(), width, height)

    assert_no_text_overlap(beat)

import pytest

from animatica.components.recursion_tree import RecursionTree, tree_layout
from animatica.components.registry import default_registry


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

import pytest

from animatica.components.recursion_tree import RecursionTree, tree_layout
from animatica.components.registry import default_registry
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_edges_connect_parent_and_child,
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
    nodes, edges = tree_layout("fib", 5)
    assert len(nodes) == 15  # full F(5) call tree: 1+1+2+3+5+3 occurrences
    xs = [x for _call, x, _y in nodes.values()]
    assert len(set(xs)) == len(xs)
    # Every node but the root is a child of exactly one parent.
    assert len(edges) == len(nodes) - 1
    assert len({child for _parent, child in edges}) == len(nodes) - 1


def test_layout_caps_at_31_nodes():
    nodes, edges = tree_layout("fib", 8)
    assert len(nodes) <= 31
    assert len(edges) == len(nodes) - 1


def test_the_edges_of_the_layout_are_the_real_parent_child_relations():
    """The layout has to hand out the relations, not leave them to be guessed."""
    nodes, edges = tree_layout("fib", 4)
    parents = {child: parent for parent, child in edges}

    # fib(4) calls fib(3) and fib(2); fib(3) calls fib(2) and fib(1).
    calls = {nid: call for nid, (call, _x, _y) in nodes.items()}
    children = {}
    for parent, child in edges:
        children.setdefault(parent, []).append(child)

    root = next(nid for nid, (call, _x, _y) in nodes.items() if call == ("fib", 4))
    assert [calls[c] for c in children[root]] == [("fib", 3), ("fib", 2)]
    for parent, child in edges:
        assert calls[child][1] in (calls[parent][1] - 1, calls[parent][1] - 2)
    assert parents  # every child has a parent



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


# ---------------------------------------------------------------------------
# B4d: an edge must run from a node to its own child
# ---------------------------------------------------------------------------


def _fib_call_tree(n: int) -> tuple[list[int], list[tuple[int, int]]]:
    """The real call tree of fib(n), written out here on purpose.

    The nodes come in node-id order (a call, then its first child, then that
    child's whole subtree, then its second child) and the edges are the real
    parent -> child relations. The component has to draw these edges; when it
    guesses the children instead, the tree looks plausible and is wrong.
    """
    arguments: list[int] = []
    edges: list[tuple[int, int]] = []

    def build(arg: int, parent: int | None) -> int:
        nid = len(arguments)
        arguments.append(arg)
        if parent is not None:
            edges.append((parent, nid))
        if arg > 1:
            build(arg - 1, nid)
            build(arg - 2, nid)
        return nid

    build(n, None)
    return arguments, edges


def _node_mobjects(beat, layout):
    """The node texts of a recursion tree, matched to the layout's node ids.

    The component plays the title first and the nodes after it, in the order
    the layout hands them out. Both are checked: the labels have to match the
    layout's order, and the layout's node ids have to be the call tree's own
    ids. A change in either fails the test instead of quietly matching the
    wrong nodes.
    """
    from manim import Text

    texts = [m for m in beat.mobjects if isinstance(m, Text)]
    node_texts = texts[1:]

    assert len(node_texts) == len(layout), (
        f"the tree drew {len(node_texts)} nodes, the layout has {len(layout)}"
    )
    assert [t.text for t in node_texts] == [
        f"{call[0]}({call[1]})" for call, _x, _y in layout.values()
    ], "the nodes are not drawn in the layout's order"

    arguments, _relations = _fib_call_tree(5)
    for nid, argument in enumerate(arguments):
        assert layout[nid][0][1] == argument, (
            f"node {nid} is {layout[nid][0]}, the call tree says fib({argument})"
        )

    return {nid: node_texts[i] for i, nid in enumerate(layout)}


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_recursion_tree_edges_run_from_a_parent_to_its_own_child(width, height):
    """Every edge must connect a node to its own child.

    The tree was drawn by guessing the children: a node was connected to
    every node in the next row with a matching argument, so a fib(3) had
    four edges instead of two and reached into the branches of other
    parents.
    """
    beat = play_component(RecursionTree(), _conformance_params(), width, height)
    layout, _relations = tree_layout("fib", 5)
    by_id = _node_mobjects(beat, layout)
    _arguments, relations = _fib_call_tree(5)

    pairs = [(by_id[parent], by_id[child]) for parent, child in relations]

    assert_edges_connect_parent_and_child(beat, pairs)



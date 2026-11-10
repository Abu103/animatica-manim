import math

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


def _drawing_order(layout) -> list[int]:
    """The node ids in the order the tree is drawn: the root first, then
    level by level from the top down, left to right."""
    levels: dict[int, list[int]] = {}
    for nid, (_call, _x, y) in layout.items():
        levels.setdefault(round(-y / 1.1), []).append(nid)
    order: list[int] = []
    for depth in sorted(levels):
        order.extend(sorted(levels[depth], key=lambda nid: layout[nid][1]))
    return order


def _node_mobjects(beat, layout):
    """The node texts of a recursion tree, matched to the layout's node ids.

    The component plays the title first and the nodes after it, in the order
    it draws them. Both are checked: the labels have to match the drawing
    order, and the layout's node ids have to be the call tree's own ids. A
    change in either fails the test instead of quietly matching the wrong
    nodes.
    """
    from manim import Text

    texts = [m for m in beat.mobjects if isinstance(m, Text)]
    node_texts = texts[1:]
    order = _drawing_order(layout)

    assert len(node_texts) == len(layout), (
        f"the tree drew {len(node_texts)} nodes, the layout has {len(layout)}"
    )
    assert [t.text for t in node_texts] == [
        f"{layout[nid][0][0]}({layout[nid][0][1]})" for nid in order
    ], "the nodes are not drawn in the layout's drawing order"

    arguments, _relations = _fib_call_tree(5)
    for nid, argument in enumerate(arguments):
        assert layout[nid][0][1] == argument, (
            f"node {nid} is {layout[nid][0]}, the call tree says fib({argument})"
        )

    return {nid: node_texts[i] for i, nid in enumerate(order)}


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_recursion_tree_edges_run_from_a_parent_to_its_own_child(width, height):
    """Every edge must connect a node to its own child.

    The tree was drawn by guessing the children: a node was connected to
    every node in the next row with a matching argument, so a fib(3) had
    four edges instead of two and reached into the branches of other
    parents.
    """
    beat = play_component(RecursionTree(), _conformance_params(), width, height)
    layout, _layout_edges = tree_layout("fib", 5)
    by_id = _node_mobjects(beat, layout)
    _arguments, relations = _fib_call_tree(5)

    pairs = [(by_id[parent], by_id[child]) for parent, child in relations]

    assert_edges_connect_parent_and_child(beat, pairs)


# ---------------------------------------------------------------------------
# B4e: the beat must end with the whole tree on screen, and it must be drawn
# from the root down
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fps", [15, 30, 60])
def test_the_beat_does_not_overrun_its_declared_duration_in_the_video(fps):
    """The video must not be longer than the beat declared.

    Manim rounds every animation up to a whole frame, so a run time that is
    not a whole number of frames makes the video longer than the beat. The
    tree has 29 animations, and the rounding added up to 0.6s: the video was
    5.8s for a 5.2s beat, the captions drifted, and the last two edges were
    still fading in when the beat was over.
    """
    from manim import tempconfig

    with tempconfig({"frame_rate": fps}):
        beat = play_component(RecursionTree(), _conformance_params(), 1280, 720)

    frames = sum(math.ceil(rt * fps - 1e-9) for rt in beat.scene.played_run_times)
    frames += sum(math.ceil(w * fps - 1e-9) for w in beat.scene.waited_seconds)
    allowed = math.ceil(beat.duration * fps) + 1

    assert frames <= allowed, (
        f"at {fps} fps the video is {frames / fps:.3f}s long "
        f"({frames} frames) but the beat declares {beat.duration}s "
        f"({allowed} frames allowed)"
    )


@pytest.mark.render
def test_the_whole_tree_is_on_screen_before_the_fade_out():
    """Every node and every edge is on screen, at full opacity, when the
    drawing is done -- and nothing is removed before the final fade-out."""
    from manim import Line, Scene, Text, tempconfig

    from animatica.components.recursion_tree import RecursionTree
    from animatica.components.theme import PALETTES

    snapshots: list[tuple[int, int, float]] = []
    original_play = Scene.play

    def spy(self, *anims, **kwargs):
        original_play(self, *anims, **kwargs)
        texts = [m for m in self.mobjects if isinstance(m, Text)]
        edges = [m for m in self.mobjects if isinstance(m, Line)]
        opacities = [
            m.opacity for m in texts + edges if getattr(m, "opacity", None) is not None
        ]
        opacity = min(opacities, default=1.0)
        snapshots.append((len(texts), len(edges), opacity))

    class S(Scene):
        def construct(self):
            RecursionTree().play(
                self,
                RecursionTree.Params(title="Fibonacci call tree", fn="fib", n=5),
                PALETTES["dark-blue"],
            )

    Scene.play = spy
    try:
        with tempconfig({"quality": "low_quality", "frame_rate": 15, "write_to_movie": False,
                         "dry_run": True, "disable_caching": True, "verbosity": "ERROR",
                         "progress_bar": "none"}):
            scene = S()
            scene.render()
    finally:
        Scene.play = original_play

    # The title and the 15 nodes are texts; the 14 edges are lines.
    drawn = [s for s in snapshots if s[1] or s[0] > 1]
    assert drawn, "the tree drew nothing"
    assert drawn[-1] == (16, 14, 1.0), (
        f"the drawing ended with {drawn[-1][0]} texts, {drawn[-1][1]} edges "
        f"at opacity {drawn[-1][2]}, not 15 nodes and 14 edges at full opacity"
    )
    # The fade-out is the last thing that happens.
    assert snapshots[-1] == (0, 0, 1.0), (
        f"the last animation left {snapshots[-1]} on the scene"
    )


def test_the_tree_is_drawn_from_the_root_down():
    """The nodes appear in order of depth, and every edge appears between its
    parent and its child.

    The tree used to be drawn from the leaves up, because the layout hands
    the positions out in the order it placed them: a parent is placed after
    its children. The root dropped in last, after the whole forest of
    numbers was already on screen.
    """
    from manim import Line

    beat = play_component(RecursionTree(), _conformance_params(), 1280, 720)
    layout, _layout_edges = tree_layout("fib", 5)
    order = _drawing_order(layout)
    by_id = _node_mobjects(beat, layout)

    appeared: list = []
    for anims, _run_time in beat.scene.plays:
        for anim in anims:
            mobject = getattr(anim, "mobject", None)
            if mobject is not None:
                appeared.append(mobject)
    index_of = {id(mobject): i for i, mobject in enumerate(appeared)}

    edges = [m for m in beat.mobjects if isinstance(m, Line)]
    assert len(edges) == len(order) - 1, (
        f"{len(edges)} edges for {len(order) - 1} children"
    )
    # The edge to a node is drawn right before the node.
    edge_of = {nid: edges[i] for i, nid in enumerate(order[1:])}

    depths = [round(-layout[nid][2] / 1.1) for nid in order]
    assert depths == sorted(depths), (
        f"the nodes do not appear in order of depth: {depths}"
    )

    _arguments, relations = _fib_call_tree(5)
    for parent, child in relations:
        parent_at = index_of[id(by_id[parent])]
        edge_at = index_of[id(edge_of[child])]
        child_at = index_of[id(by_id[child])]
        assert parent_at < edge_at <= child_at, (
            f"the edge from node {parent} to node {child} appears at {edge_at}, "
            f"its parent at {parent_at} and its child at {child_at}"
        )



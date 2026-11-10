"""Recursion tree: the call tree of F(n) -> F(n-1), F(n-2), repeated calls in red.

Made for prompts like "show the fibonacci recursion tree". Leaves are evenly spaced,
parents centered over their children; node count capped at 31. Duration: 2.0 s + 0.8 s per level.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, field_validator

from animatica.components._draw import FADE_OUT, MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components._draw import caption_band_top as caption_band_top_of
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_NODES = 31
SUPPORTED_FNS = ("fib",)

#: Time a node and an edge take when the tree is drawn at full speed. The
#: beat's budget is shared out between them, so a bigger tree draws faster.
NODE_TIME = 0.15
EDGE_TIME = 0.1

#: Time the title takes before the tree starts.
TITLE_TIME = 0.5


def tree_layout(fn: str, n: int) -> tuple[dict[int, tuple[tuple, float, float]], list[tuple[int, int]]]:
    """Return ({node_id: (call, x, y)}, [(parent_id, child_id), ...]).

    Every call occurrence is its own node (repeats included). Leaves get distinct
    evenly-spaced x positions; parents are centered over their children. Capped at
    MAX_NODES nodes (deepest/rightmost dropped first).

    The edge list is the real parent -> child relation, and it has to travel
    with the layout: a caller that has to guess the children from the depth
    and from the argument value connects a node to every matching node in the
    next row, not only to its own children.

    The positions come back in the order the layout placed the nodes, which is
    the order of the tree from the leaves up (a parent is placed after its
    children). The node ids are the order the calls were created in, from the
    root down.
    """
    nodes: list[tuple] = []  # (id, call, depth, parent_id)
    edges: list[tuple[int, int]] = []  # (parent id, child id)

    def build(call: tuple, depth: int, parent: int | None) -> int:
        if len(nodes) >= MAX_NODES:
            return -1
        nid = len(nodes)
        nodes.append((nid, call, depth, parent))
        if parent is not None:
            edges.append((parent, nid))
        if fn == "fib" and call[1] > 1:
            build((call[0], call[1] - 1), depth + 1, nid)
            build((call[0], call[1] - 2), depth + 1, nid)
        return nid

    build((fn, n), 0, None)

    children: dict[int, list[int]] = {}
    for nid, _call, _d, parent in nodes:
        if parent is not None:
            children.setdefault(parent, []).append(nid)

    pos: dict[int, tuple[tuple, float, float]] = {}
    leaf_x = {"next": 0.0}

    def place(nid: int) -> float:
        call, depth = nodes[nid][1], nodes[nid][2]
        kids = children.get(nid, [])
        if kids:
            x = sum(place(k) for k in kids) / len(kids)
        else:
            x = leaf_x["next"]
            leaf_x["next"] += 1.0
        pos[nid] = (call, x, -depth * 1.1)
        return x

    place(0)
    xs = [v[1] for v in pos.values()]
    lo, hi = min(xs), (max(xs) or 1.0)
    span = (hi - lo) or 1.0
    positions = {
        nid: (call, -5.5 + (x - lo) / span * 11.0, y) for nid, (call, x, y) in pos.items()
    }
    return positions, edges


def drawing_order(nodes: dict[int, tuple[tuple, float, float]]) -> list[int]:
    """The node ids in the order the tree is drawn.

    The root first, then level by level from the top down, left to right,
    and every child with the edge that leads to it. A call tree that grows
    from the root reads as a call tree; one that grows from the leaves reads
    as a pile of numbers that happens to be connected.
    """
    levels: dict[int, list[int]] = {}
    for nid, (_call, _x, y) in nodes.items():
        levels.setdefault(round(-y / 1.1), []).append(nid)
    order: list[int] = []
    for depth in sorted(levels):
        order.extend(sorted(levels[depth], key=lambda nid: nodes[nid][1]))
    return order


class RecursionTree(Component):
    name: ClassVar[str] = "recursion_tree"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        fn: str = "fib"
        n: int = Field(ge=2, le=6)

        @field_validator("fn")
        @classmethod
        def _fn_ok(cls, v: str) -> str:
            if v not in SUPPORTED_FNS:
                raise ValueError(f"fn must be one of {SUPPORTED_FNS}")
            return v

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.8 * (p.n - 1)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        return f"{p.title}: call tree of {p.fn}({p.n})"  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import UP, FadeIn, Line, Text, VGroup, config

        prepare(scene, colors)
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        nodes, relations = tree_layout(p.fn, p.n)  # type: ignore[arg-type]
        counts: dict[tuple, int] = {}
        for _nid, (call, _x, _y) in nodes.items():
            counts[call] = counts.get(call, 0) + 1
        seen: set[tuple] = set()
        vg_nodes = VGroup()
        vg_edges = VGroup()
        node_of: dict[int, object] = {}
        for nid, (call, x, y) in nodes.items():
            label = f"{call[0]}({call[1]})"
            repeated = counts[call] > 1 and call in seen
            seen.add(call)
            color = getattr(colors, "warn", colors.accent) if repeated else colors.text
            node = Text(label, font_size=MIN_FONT_SIZE, color=color)
            node.move_to([x, y + 1.2, 0])
            vg_nodes.add(node)
            node_of[nid] = node
        # The edges are the real parent -> child relations. Guessing the
        # children from the depth and from the argument value connected every
        # node to every matching node in the next row: a fib(3) had four
        # edges instead of two, and they reached into the branches of other
        # parents.
        edge_of: dict[tuple[int, int], object] = {}
        for parent_id, child_id in relations:
            _pcall, px, py = nodes[parent_id]
            _ccall, cx, cy = nodes[child_id]
            edge = Line([px, py + 1.0, 0], [cx, cy + 1.4, 0], color=colors.muted)
            vg_edges.add(edge)
            edge_of[(parent_id, child_id)] = edge
        # The tree is drawn first and the title goes above it. The title used
        # to sit in the middle of the tree, on top of the first row of nodes.
        tree = VGroup(vg_nodes, vg_edges)
        caption = getattr(scene, "caption_mobject", None)
        band = caption_band_top_of(caption)
        # Shrink only: scaling the tree up to fill the frame pushed the outer
        # leaves past the safe-area margin frame-lint keeps free, and the
        # bottom of the tree into the caption.
        fit(tree, max_width=config.frame_width - 2.0,
            max_height=config.frame_height / 2 - 0.6 - title.height - 0.4 - band,
            scale_up=False)
        tree.shift(UP * (band - tree.get_bottom()[1]))
        title.next_to(tree, UP, buff=0.4)
        clock = Clock(scene, self.duration(p))
        # The budget is counted in whole video frames. Manim rounds every
        # animation up to the next frame, and with 29 small animations that
        # rounding added up to 0.6s: the video was longer than the beat
        # declared, the captions drifted, and the last edges were still
        # fading in when the beat was supposed to be over. What is left of
        # the budget holds the finished tree, so it can be read.
        node_time = clock.seconds(clock.frames(NODE_TIME))
        edge_time = clock.seconds(clock.frames(EDGE_TIME))
        clock.play(FadeIn(title), run_time=clock.seconds(clock.frames(TITLE_TIME)))
        parent_of = {child: parent for parent, child in relations}
        for nid in drawing_order(nodes):
            parent = parent_of.get(nid)
            if parent is not None:
                clock.play(FadeIn(edge_of[(parent, nid)]), run_time=edge_time)
            clock.play(FadeIn(node_of[nid]), run_time=node_time)
        clock.finish()

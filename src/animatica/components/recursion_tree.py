"""Recursion tree: the call tree of F(n) -> F(n-1), F(n-2), repeated calls in red.

Made for prompts like "show the fibonacci recursion tree". Leaves are evenly spaced,
parents centered over their children; node count capped at 31. Duration: 2.0 s + 0.8 s per level.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, field_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_NODES = 31
SUPPORTED_FNS = ("fib",)


def tree_layout(fn: str, n: int) -> dict[int, tuple[tuple, float, float]]:
    """Return {node_id: (call, x, y)} for the call tree of fn(n).

    Every call occurrence is its own node (repeats included). Leaves get distinct
    evenly-spaced x positions; parents are centered over their children. Capped at
    MAX_NODES nodes (deepest/rightmost dropped first).
    """
    nodes: list[tuple] = []  # (id, call, depth, parent_id)

    def build(call: tuple, depth: int, parent: int | None) -> int:
        if len(nodes) >= MAX_NODES:
            return -1
        nid = len(nodes)
        nodes.append((nid, call, depth, parent))
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
    return {nid: (call, -5.5 + (x - lo) / span * 11.0, y) for nid, (call, x, y) in pos.items()}


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
        from manim import FadeIn, Line, Text, VGroup

        prepare(scene, colors)
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        nodes = tree_layout(p.fn, p.n)  # type: ignore[arg-type]
        counts: dict[tuple, int] = {}
        for _nid, (call, _x, _y) in nodes.items():
            counts[call] = counts.get(call, 0) + 1
        seen: set[tuple] = set()
        vg_nodes = VGroup()
        vg_edges = VGroup()
        for nid, (call, x, y) in nodes.items():
            label = f"{call[0]}({call[1]})"
            repeated = counts[call] > 1 and call in seen
            seen.add(call)
            color = getattr(colors, "warn", colors.accent) if repeated else colors.text
            node = Text(label, font_size=MIN_FONT_SIZE, color=color)
            node.move_to([x, y + 1.2, 0])
            vg_nodes.add(node)
        for nid, (call, x, y) in nodes.items():
            if p.fn == "fib" and call[1] > 1:  # type: ignore[operator]
                for _c_nid, (ccall, cx, cy) in nodes.items():
                    if ccall[1] == call[1] - 1 or ccall[1] == call[1] - 2:  # type: ignore[operator]
                        # edge to direct children only: check depth difference
                        pass
        # simpler: edges from parent to its two fib children by depth
        by_depth: dict[int, list[int]] = {}
        for nid, (call, _x, y) in nodes.items():
            by_depth.setdefault(round(-y / 1.1), []).append(nid)
        for nid, (call, x, y) in nodes.items():
            d = round(-y / 1.1)
            if p.fn == "fib" and call[1] > 1:  # type: ignore[operator]
                for cid in by_depth.get(d + 1, []):
                    ccall, cx, cy = nodes[cid]
                    if ccall[1] in (call[1] - 1, call[1] - 2):  # type: ignore[operator]
                        vg_edges.add(Line([x, y + 1.0, 0], [cx, cy + 1.4, 0], color=colors.muted))
        group = VGroup(title, vg_nodes, vg_edges)
        fit(group)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.5)
        for node in vg_nodes:
            clock.play(FadeIn(node), run_time=0.15)
        for edge in vg_edges:
            clock.play(FadeIn(edge), run_time=0.1)
        clock.finish()

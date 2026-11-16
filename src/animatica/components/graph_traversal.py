"""Graph traversal: a small graph, walked breadth-first or depth-first from a start node.

Made for prompts like "BFS on a small graph" or "show depth-first search order". The visit order is
computed (neighbours are taken in `nodes` order, so ties are always broken the same way), never typed in,
so it is always correct. Nodes sit in columns by hop distance from the start; each visit lights the node,
the edge it was reached by, and its place in the order. Unreachable nodes stay dim.
Duration: 2.5 s + 0.6 s per visited node.
"""
from __future__ import annotations

from collections import deque
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit_in_room, prepare
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_LABEL = 4
MAX_NODES = 8
MAX_EDGES = 12


class GraphTraversal(Component):
    name: ClassVar[str] = "graph_traversal"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        nodes: list[str] = Field(min_length=2, max_length=MAX_NODES)
        edges: list[list[str]] = Field(default_factory=list, max_length=MAX_EDGES, description="pairs of node labels")
        start: str | None = Field(default=None, description="node to start from; the first node if omitted")
        order: Literal["bfs", "dfs"] = "bfs"
        directed: bool = False

        @model_validator(mode="after")
        def _check(self):
            for n in self.nodes:
                if not n.strip() or len(n) > MAX_LABEL:
                    raise ValueError(f"node label {n!r} must be 1-{MAX_LABEL} characters")
            if len({n.strip().lower() for n in self.nodes}) != len(self.nodes):
                raise ValueError("node labels must differ")
            known = set(self.nodes)
            seen: set[tuple[str, ...]] = set()
            for e in self.edges:
                if len(e) != 2:
                    raise ValueError(f"edge {e} must be a pair of node labels")
                a, b = e
                for x in (a, b):
                    if x not in known:
                        raise ValueError(f"edge {e} uses {x!r}, which is not in nodes")
                if a == b:
                    raise ValueError(f"edge {e} joins a node to itself")
                key = (a, b) if self.directed else tuple(sorted((a, b)))
                if key in seen:
                    raise ValueError(f"edge {a}-{b} is given twice")
                seen.add(key)
            if self.start is None:
                self.start = self.nodes[0]
            elif self.start not in known:
                raise ValueError(f"start {self.start!r} is not in nodes")
            return self

    @staticmethod
    def _adjacency(p: BaseModel) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {n: [] for n in p.nodes}  # type: ignore[attr-defined]
        for a, b in p.edges:  # type: ignore[attr-defined]
            adj[a].append(b)
            if not p.directed:  # type: ignore[attr-defined]
                adj[b].append(a)
        rank = {n: i for i, n in enumerate(p.nodes)}  # type: ignore[attr-defined]
        for n in adj:
            adj[n].sort(key=rank.__getitem__)
        return adj

    @staticmethod
    def traverse(p: BaseModel) -> list[tuple[str, str | None]]:
        """The visit order as (node, node it was reached from), neighbours taken in `nodes` order."""
        adj = GraphTraversal._adjacency(p)
        start = p.start  # type: ignore[attr-defined]
        visited: list[tuple[str, str | None]] = []
        seen = {start}
        if p.order == "bfs":  # type: ignore[attr-defined]
            queue = deque([(start, None)])
            while queue:
                node, parent = queue.popleft()
                visited.append((node, parent))
                for nb in adj[node]:
                    if nb not in seen:
                        seen.add(nb)
                        queue.append((nb, node))
        else:
            def go(node: str, parent: str | None) -> None:
                visited.append((node, parent))
                for nb in adj[node]:
                    if nb not in seen:
                        seen.add(nb)
                        go(nb, node)
            go(start, None)
        return visited

    @staticmethod
    def layers(p: BaseModel) -> dict[str, int]:
        """Hop distance from the start (the column of each node); unreachable nodes get the last column."""
        adj = GraphTraversal._adjacency(p)
        dist = {p.start: 0}  # type: ignore[attr-defined]
        queue = deque([p.start])  # type: ignore[attr-defined]
        while queue:
            node = queue.popleft()
            for nb in adj[node]:
                if nb not in dist:
                    dist[nb] = dist[node] + 1
                    queue.append(nb)
        last = max(dist.values()) + 1
        return {n: dist.get(n, last) for n in p.nodes}  # type: ignore[attr-defined]

    def duration(self, p: BaseModel) -> float:
        return 2.5 + 0.6 * len(self.traverse(p))

    def fallback_text(self, p: BaseModel) -> str:
        return f"{p.title}\n" + " → ".join(n for n, _ in self.traverse(p))  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import (DOWN, UP, Circle, FadeIn, Line, Text, VGroup, Arrow)

        prepare(scene, colors)
        layer = self.layers(p)
        order = self.traverse(p)
        visited = {n for n, _ in order}
        columns: dict[int, list[str]] = {}
        for n in p.nodes:
            columns.setdefault(layer[n], []).append(n)

        dx, dy = 2.4, 1.3
        pos = {}
        for col, names in columns.items():
            for r, n in enumerate(names):
                pos[n] = [(col - (len(columns) - 1) / 2) * dx, ((len(names) - 1) / 2 - r) * dy, 0]

        def disc(label: str, lit: bool):
            text = Text(label, font_size=32, color=colors.text if lit else colors.muted)
            ring = Circle(radius=max(0.42, text.width / 2 + 0.18), stroke_color=colors.accent if lit else colors.muted,
                          stroke_width=4, fill_color=colors.background, fill_opacity=1.0)
            return VGroup(ring, text)

        dim = {n: disc(n, False).move_to(pos[n]) for n in p.nodes}
        lit = {n: disc(n, True).move_to(pos[n]) for n in p.nodes}

        def edge_between(a: str, b: str, color: str, width: float):
            ra, rb = dim[a][0].radius, dim[b][0].radius
            va = [pos[b][i] - pos[a][i] for i in range(2)]
            norm = (va[0] ** 2 + va[1] ** 2) ** 0.5 or 1.0
            start = [pos[a][0] + va[0] / norm * ra, pos[a][1] + va[1] / norm * ra, 0]
            end = [pos[b][0] - va[0] / norm * rb, pos[b][1] - va[1] / norm * rb, 0]
            if p.directed:
                return Arrow(start, end, buff=0, color=color, stroke_width=width, max_tip_length_to_length_ratio=0.2)
            return Line(start, end, color=color, stroke_width=width)

        base_edges = [edge_between(a, b, colors.muted, 3) for a, b in p.edges]
        graph = VGroup(*base_edges, *dim.values())
        title = Text(p.title, font_size=40, color=colors.text)
        badges = {}
        for i, (n, _) in enumerate(order, 1):
            badges[n] = Text(str(i), font_size=32, color=colors.accent2, weight="BOLD").next_to(lit[n], UP, buff=0.1)
        tree_edges = {n: edge_between(par, n, colors.accent, 5) for n, par in order if par is not None}
        body = VGroup(title, VGroup(graph, *tree_edges.values(), *lit.values(), *badges.values())).arrange(DOWN, buff=0.5)
        fit_in_room(scene, body)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), FadeIn(graph), run_time=clock.whole(0.8))
        for n, _ in order:
            anims = [FadeIn(lit[n]), FadeIn(badges[n])]
            if n in tree_edges:
                anims.append(FadeIn(tree_edges[n]))
            clock.play(*anims, run_time=clock.whole(0.6))
        _ = visited
        clock.finish()

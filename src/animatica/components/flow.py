"""Flow diagram: nodes and edges with flowchart-style layout.

Made for prompts like "flow diagram from A to B to C" or "show the process flow".
Improved over `diagram`: auto-layouts nodes vertically, supports curved edges,
and has distinct node styling. Better for sequential processes.
Duration: 2.0 s + 0.6 s per edge.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit, fit_in_room, prepare
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_NODES = 10
MAX_EDGES = 12


class Flow(Component):
    name: ClassVar[str] = "flow"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        nodes: list[str] = Field(min_length=1, max_length=MAX_NODES)
        edges: list[list[int]] = Field(
            default_factory=list,
            description="edges as [from_index, to_index] pairs (0-based)",
        )

        @model_validator(mode="after")
        def _check(self):
            n = len(self.nodes)
            for edge in self.edges:
                if len(edge) != 2:
                    raise ValueError(f"edge {edge} must be [from, to]")
                frm, to = edge
                if not (0 <= frm < n and 0 <= to < n):
                    raise ValueError(f"edge {edge} node index out of range for {n} nodes")
                if frm == to:
                    raise ValueError(
                        f"edge {edge} is a self-loop; self-loops are not supported"
                    )
            if len(self.edges) > MAX_EDGES:
                raise ValueError(f"at most {MAX_EDGES} edges")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.6 * len(p.edges)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        node_list = " -> ".join(p.nodes)  # type: ignore[attr-defined]
        return f"{p.title}\\n{node_list}"

    def play(self, scene, p, colors) -> None:
        from manim import Arrow, Circle, DOWN, FadeIn, Text, UP, VGroup

        prepare(scene, colors)
        nodes = p.nodes  # type: ignore[attr-defined]
        edges = p.edges  # type: ignore[attr-defined]
        n = len(nodes)

        title = Text(p.title, font_size=40, color=colors.text).to_edge(UP, buff=0.4)
        fit(title)

        # --- Create nodes and lay them out vertically ---
        node_mobs: list = []
        spacing = 1.4
        total_height = (n - 1) * spacing
        start_y = total_height / 2

        for i, node_text in enumerate(nodes):
            circle = Circle(radius=0.5, stroke_color=colors.muted, stroke_width=2)
            circle.set_fill(colors.background, opacity=0)
            label = Text(node_text, font_size=28, color=colors.text)
            if label.width > 0.9:
                label.scale_to_fit_width(0.9)
            group = VGroup(circle, label)
            group.move_to([0, start_y - i * spacing, 0])
            node_mobs.append(group)

        # Group all nodes and fit as a unit so their final positions are stable
        all_nodes = VGroup(*node_mobs)
        fit(all_nodes)

        # --- Create arrows from final node positions (after fit) ---
        arrows: list = []
        seen_edges: set[tuple[int, int]] = set()
        for frm, to in edges:
            # Reject duplicate edges (same direction).
            if (frm, to) in seen_edges:
                raise ValueError(f"duplicate edge {frm}->{to} in flow diagram")
            seen_edges.add((frm, to))

            # For backward edges (from > to), draw from source top to
            # destination bottom so arrows always point the right way.
            # For forward edges, use source bottom -> destination top.
            if frm < to:
                start = node_mobs[frm].get_bottom()
                end = node_mobs[to].get_top()
            elif frm > to:
                start = node_mobs[frm].get_top()
                end = node_mobs[to].get_bottom()
            else:
                # frm == to is already rejected by the validator, but keep
                # a defensive branch for robustness.
                continue

            arrow = Arrow(start, end, buff=0.55, color=colors.accent, stroke_width=3)
            arrows.append(arrow)

        # --- Group nodes + arrows together so they move/scale as one unit ---
        diagram = VGroup(all_nodes, *arrows)
        fit(diagram)

        # --- Arrange title + diagram ---
        whole = VGroup(title, diagram).arrange(DOWN, buff=0.6)
        fit_in_room(scene, whole)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        per = max(0.2, 1.2 / n)
        for mob in node_mobs:
            clock.play(FadeIn(mob), run_time=per)
        per_arrow = max(0.15, 1.0 / max(len(arrows), 1))
        for arrow in arrows:
            clock.play(FadeIn(arrow), run_time=per_arrow)
        clock.finish()

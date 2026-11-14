"""Diagram: nodes and arrows drawn on, laid out left to right.
1.0 s + 0.6 s per edge."""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, prepare
from animatica.components.base import Component
from animatica.components.theme import ThemeColors
from animatica.native import layout_graph


class Diagram(Component):
    name: ClassVar[str] = "diagram"

    class Params(BaseModel):
        nodes: list[str] = Field(min_length=2, max_length=10)
        edges: list[tuple[str, str]] = Field(default_factory=list)

        @model_validator(mode="after")
        def _check_edges(self):
            node_set = set(self.nodes)
            for a, b in self.edges:
                if a not in node_set or b not in node_set:
                    raise ValueError(f"Edge ({a!r}, {b!r}) references unknown node")
            return self

    def duration(self, p: BaseModel) -> float:
        return 1.0 + 0.6 * len(p.edges)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [f"Nodes: {', '.join(p.nodes)}"]  # type: ignore[attr-defined]
        if p.edges:  # type: ignore[attr-defined]
            lines.append("Edges: " + ", ".join(f"{a}->{b}" for a, b in p.edges))
        return "\n".join(lines)

    def play(self, scene, p, colors: ThemeColors) -> None:
        import math

        from manim import Arrow, Circle, FadeIn, Text

        prepare(scene, colors)
        width, height = 11.5, 4.4
        raw = layout_graph(p.nodes, p.edges, width, height)  # type: ignore[attr-defined]
        # layout_graph works in [0,width]x[0,height]; Manim's origin is the frame centre.
        positions = {n: (x - width / 2, y - height / 2 + 0.3) for n, (x, y) in raw.items()}

        pts = list(positions.values())
        gaps = [math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]]
        pitch = min(gaps) if gaps else 2.0
        radius = max(0.18, min(0.38, 0.24 * pitch))

        node_mobjects = {}
        for node in p.nodes:  # type: ignore[attr-defined]
            x, y = positions[node]
            circle = Circle(radius=radius)
            circle.move_to([x, y, 0])
            circle.set_fill(colors.accent, opacity=1.0)
            circle.set_stroke(colors.text, width=2)
            label = Text(node, font_size=28, color=colors.text)
            if label.width <= 1.5 * radius:  # short label: sits inside the circle
                label.move_to([x, y, 0])
                label.set_color(colors.background)
            else:  # long label: sits under the circle and is squeezed to its own column
                max_w = max(0.6, min(pitch * 0.82, 3.0))
                if label.width > max_w:
                    label.scale_to_fit_width(max_w)
                label.move_to([x, y - radius - 0.1 - label.height / 2, 0])
            node_mobjects[node] = (circle, label)

        total = self.duration(p)  # type: ignore[attr-defined]
        edge_t = 0.3
        # Fit every fade into the declared duration (minus the closing fade) so captions stay in sync.
        node_t = max(0.1, min(0.4, (total - 0.4 - edge_t * len(p.edges)) / len(p.nodes)))  # type: ignore[attr-defined]
        clock = Clock(scene, total)
        for node in p.nodes:  # type: ignore[attr-defined]
            circle, label = node_mobjects[node]
            clock.play(FadeIn(circle), FadeIn(label), run_time=node_t)

        for a, b in p.edges:  # type: ignore[attr-defined]
            ax, ay = positions[a]
            bx, by = positions[b]
            arrow = Arrow([ax, ay, 0], [bx, by, 0], color=colors.text, buff=radius + 0.04,
                          stroke_width=5, max_tip_length_to_length_ratio=0.4, max_stroke_width_to_length_ratio=12)
            clock.play(FadeIn(arrow), run_time=edge_t)

        clock.finish()


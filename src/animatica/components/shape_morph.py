"""Shape morph: one shape transforms into another. 3.0 s."""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from animatica.components._draw import Clock, fit, prepare
from animatica.components.base import Component
from animatica.components.theme import ThemeColors


class ShapeMorph(Component):
    name: ClassVar[str] = "shape_morph"

    class Params(BaseModel):
        from_shape: Literal["circle", "square", "triangle", "star"]
        to_shape: Literal["circle", "square", "triangle", "star"]
        from_color: str = Field("", description="defaults to theme accent")
        to_color: str = Field("", description="defaults to theme accent2")

    def duration(self, p: BaseModel) -> float:
        return 3.0

    def fallback_text(self, p: BaseModel) -> str:
        return f"{p.from_shape} -> {p.to_shape}"  # type: ignore[attr-defined]

    def _shape(self, kind: str, size: float = 1.2):
        from manim import Circle, Polygon, Square, Star

        if kind == "circle":
            return Circle(radius=size / 2)
        if kind == "square":
            return Square(side_length=size)
        if kind == "triangle":
            return Polygon(*[(0, 1, 0), (-0.87, -0.5, 0), (0.87, -0.5, 0)])
        if kind == "star":
            return Star(n=5, outer_radius=size / 2, inner_radius=size / 4)
        raise ValueError(f"Unknown shape: {kind}")

    def play(self, scene, p, colors: ThemeColors) -> None:
        from manim import FadeIn, ReplacementTransform

        prepare(scene, colors)
        from_color = p.from_color or colors.accent
        to_color = p.to_color or colors.accent2

        start = self._shape(p.from_shape)
        start.set_fill(from_color, opacity=1.0)
        start.set_stroke(width=0)
        end = self._shape(p.to_shape)
        end.set_fill(to_color, opacity=1.0)
        end.set_stroke(width=0)
        fit(end)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(start), run_time=0.8)
        clock.wait(0.7)
        clock.play(ReplacementTransform(start, end), run_time=1.0)
        clock.finish()


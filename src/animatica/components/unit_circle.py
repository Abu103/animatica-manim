"""Unit circle: 1-4 special angles marked on the circle, each with its exact (cos, sin).

Made for prompts like "show the unit circle at 30, 45 and 60 degrees" or "sine and cosine of the special angles".
Angles are the special ones, multiples of 30 or 45 degrees in [0, 360), so every point has an exact
value (√3/2, 1/2, ...) rather than a rounded decimal; the values are looked up, never typed in, so they
are always right. `units` chooses degrees or radians for the labels.
Duration: 2.5 s + 0.9 s per angle.
"""
from __future__ import annotations

from math import gcd
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit_in_room, prepare
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

# exact cos/sin of the first-quadrant special angles
_COS = {0: "1", 30: "√3/2", 45: "√2/2", 60: "1/2", 90: "0"}
_SIN = {0: "0", 30: "1/2", 45: "√2/2", 60: "√3/2", 90: "1"}


class UnitCircle(Component):
    name: ClassVar[str] = "unit_circle"

    ALLOWED: ClassVar[tuple[int, ...]] = tuple(d for d in range(360) if d % 30 == 0 or d % 45 == 0)

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        angles: list[int] = Field(min_length=1, max_length=4, description="degrees, multiples of 30 or 45 in [0, 360)")
        units: Literal["degrees", "radians"] = "degrees"

        @model_validator(mode="after")
        def _check(self):
            for a in self.angles:
                if a not in UnitCircle.ALLOWED:
                    raise ValueError(f"angle {a} is not a special angle: use multiples of 30 or 45 degrees from 0 to 330")
            if len(set(self.angles)) != len(self.angles):
                raise ValueError("angles must differ")
            return self

    @staticmethod
    def exact_xy(deg: int) -> tuple[str, str]:
        """Exact (cos, sin) as text, e.g. 120 -> ('-1/2', '√3/2')."""
        def signed(mag: str, negative: bool) -> str:
            return "-" + mag if negative and mag != "0" else mag

        if deg % 90 == 0:  # on an axis
            return {0: ("1", "0"), 90: ("0", "1"), 180: ("-1", "0"), 270: ("0", "-1")}[deg]
        quadrant = deg // 90
        ref = (deg, 180 - deg, deg - 180, 360 - deg)[quadrant]
        return signed(_COS[ref], quadrant in (1, 2)), signed(_SIN[ref], quadrant in (2, 3))

    @staticmethod
    def radians_label(deg: int) -> str:
        """deg as a reduced fraction of pi, e.g. 210 -> '7π/6'."""
        if deg == 0:
            return "0"
        g = gcd(deg, 180)
        num, den = deg // g, 180 // g
        top = "π" if num == 1 else f"{num}π"
        return top if den == 1 else f"{top}/{den}"

    def _label(self, p: BaseModel, deg: int) -> str:
        return self.radians_label(deg) if p.units == "radians" else f"{deg}°"  # type: ignore[attr-defined]

    def duration(self, p: BaseModel) -> float:
        return 2.5 + 0.9 * len(p.angles)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [p.title]  # type: ignore[attr-defined]
        for deg in p.angles:  # type: ignore[attr-defined]
            x, y = self.exact_xy(deg)
            lines.append(f"{self._label(p, deg)}: ({x}, {y})")
        return "\n".join(lines)

    def play(self, scene, p, colors) -> None:
        import numpy as np
        from manim import DOWN, LEFT, RIGHT, Arc, Circle, Dot, FadeIn, Line, Text, VGroup

        prepare(scene, colors)
        radius = 2.1
        shade = [colors.accent, colors.accent2, colors.text, "#7ee787"]  # four distinct colours; muted is the circle's own
        origin = np.array([0.0, 0.0, 0.0])

        circle = Circle(radius=radius, stroke_color=colors.muted, stroke_width=4)
        axes = VGroup(Line([-radius - 0.4, 0, 0], [radius + 0.4, 0, 0], color=colors.muted, stroke_width=2),
                      Line([0, -radius - 0.4, 0], [0, radius + 0.4, 0], color=colors.muted, stroke_width=2))
        base = VGroup(circle, axes)

        marks, rows = [], []
        for i, deg in enumerate(p.angles):
            theta = np.radians(deg)
            point = origin + radius * np.array([np.cos(theta), np.sin(theta), 0.0])
            spoke = Line(origin, point, color=shade[i], stroke_width=5)
            arc = Arc(radius=0.55 + 0.17 * i, start_angle=0, angle=theta, color=shade[i], stroke_width=4) if deg else None
            dot = Dot(point, color=shade[i], radius=0.11)
            tag = Text(self._label(p, deg), font_size=32, color=shade[i])
            tag.move_to(point + np.array([np.cos(theta), np.sin(theta), 0.0]) * 0.55)
            marks.append(VGroup(*[m for m in (spoke, arc, dot, tag) if m is not None]))
            x, y = self.exact_xy(deg)
            rows.append(Text(f"{self._label(p, deg)}: ({x}, {y})", font_size=32, color=shade[i]))

        panel = VGroup(*rows).arrange(DOWN, buff=0.35, aligned_edge=LEFT)
        panel.next_to(base, RIGHT, buff=1.0)
        diagram = VGroup(base, *marks, panel)
        body = VGroup(Text(p.title, font_size=40, color=colors.text), diagram).arrange(DOWN, buff=0.4)
        fit_in_room(scene, body)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(body[0]), FadeIn(base), run_time=clock.whole(0.8))
        for mark, row in zip(marks, rows):
            clock.play(FadeIn(mark), FadeIn(row), run_time=clock.whole(0.9))
        clock.finish()

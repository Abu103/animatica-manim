"""Pie or donut chart: 2-6 slices, each labelled with its share.

Made for prompts like "pie chart of browser market share" or "donut chart of where the budget goes".
Values are proportions of the whole, in any unit; the chart shows each slice's percent (whole numbers
that always add up to 100). A slice under 3% is rejected: its label would sit on its neighbours', so
merge small ones into an "Other" slice. `donut` cuts a hole in the middle that can hold a short `center` text.
Duration: 2.0 s + 0.5 s per slice.
"""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit_in_room, prepare
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_LABEL = 24
MIN_SHARE = 0.03


class Slice(BaseModel):
    label: str = Field(min_length=1, max_length=MAX_LABEL)
    value: float = Field(gt=0.0, description="size of the slice, any unit; only the proportion matters")

    @model_validator(mode="after")
    def _finite(self):
        if not math.isfinite(self.value):
            raise ValueError("value must be a finite number")
        return self


class PieDonut(Component):
    name: ClassVar[str] = "pie_donut"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        slices: list[Slice] = Field(min_length=2, max_length=6)
        donut: bool = False
        center: str | None = Field(default=None, max_length=16, description="text inside a donut's hole")

        @model_validator(mode="after")
        def _check(self):
            if len({s.label.strip().lower() for s in self.slices}) != len(self.slices):
                raise ValueError("slice labels must differ")
            total = sum(s.value for s in self.slices)
            for s in self.slices:
                if s.value / total < MIN_SHARE:
                    raise ValueError(
                        f"slice {s.label!r} is under {MIN_SHARE:.0%} of the whole, too thin to label: "
                        "merge small slices into one called 'Other'")
            return self

    @staticmethod
    def percentages(values: list[float]) -> list[int]:
        """Whole-number percents that sum to exactly 100 (largest-remainder method, ties by order)."""
        total = sum(values)
        raw = [v / total * 100 for v in values]
        floors = [int(r) for r in raw]
        by_remainder = sorted(range(len(raw)), key=lambda i: (-(raw[i] - floors[i]), i))
        for i in by_remainder[: 100 - sum(floors)]:
            floors[i] += 1
        return floors

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.5 * len(p.slices)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        pct = self.percentages([s.value for s in p.slices])  # type: ignore[attr-defined]
        lines = [p.title]  # type: ignore[attr-defined]
        lines += [f"  {s.label}: {c}%" for s, c in zip(p.slices, pct)]  # type: ignore[attr-defined]
        return "\n".join(lines)

    def play(self, scene, p, colors) -> None:
        import numpy as np
        from manim import (DOWN, LEFT, RIGHT, UP, AnnularSector, FadeIn, ManimColor, Text, VGroup,
                           interpolate_color)

        prepare(scene, colors)
        c = {k: ManimColor(getattr(colors, k)) for k in ("accent", "accent2", "muted", "text")}
        palette = [c["accent"], c["accent2"], c["muted"],
                   interpolate_color(c["accent"], c["text"], 0.55),
                   interpolate_color(c["accent2"], c["text"], 0.55),
                   interpolate_color(c["accent"], c["accent2"], 0.5)]
        pct = self.percentages([s.value for s in p.slices])
        total = sum(s.value for s in p.slices)
        outer, inner = 2.0, (1.1 if p.donut else 0.0)

        angle = np.pi / 2  # start at the top, go clockwise
        parts: list = []
        for i, s in enumerate(p.slices):
            sweep = s.value / total * 2 * np.pi
            sector = AnnularSector(inner_radius=inner, outer_radius=outer, angle=-sweep,
                                   start_angle=angle, fill_color=palette[i], fill_opacity=0.9,
                                   stroke_color=colors.background, stroke_width=3)
            mid = angle - sweep / 2
            direction = np.array([np.cos(mid), np.sin(mid), 0.0])
            label = Text(f"{s.label} {pct[i]}%", font_size=32, color=colors.text)
            at = direction * (outer + 0.25)
            label.move_to(at + direction * 0.0)
            # anchor the text's near edge to the ring, so it grows away from the pie
            label.next_to(at, RIGHT if direction[0] >= 0 else LEFT, buff=0.0)
            if abs(direction[1]) > 0.93:  # straight above/below: centre it over the slice
                label.next_to(at, UP if direction[1] > 0 else DOWN, buff=0.1)
            parts.append(VGroup(sector, label))
            angle -= sweep

        chart = VGroup(*parts)
        if p.donut and p.center:  # appears with the first slice
            hole = Text(p.center, font_size=32, color=colors.text).move_to([0, 0, 0])
            parts[0].add(hole)
            chart.add(hole)
        body = VGroup(Text(p.title, font_size=40, color=colors.text), chart).arrange(DOWN, buff=0.45)
        fit_in_room(scene, body)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(body[0]), run_time=clock.whole(0.6))
        for g in parts:
            clock.play(FadeIn(g), run_time=clock.whole(0.5))
        clock.finish()

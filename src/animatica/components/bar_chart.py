"""Bar chart: bars grow from a shared baseline, then value labels appear. 2.0 s + 0.3 s per bar."""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare
from animatica.components._draw import caption_band_top as caption_band_top_of
from animatica.components._scale import NOTES, Scale, scaled_heights
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_BARS = 12
BASELINE_Y = -2.2
MAX_BAR_HEIGHT = 3.6


class BarChart(Component):
    name: ClassVar[str] = "bar_chart"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        labels: list[str] = Field(min_length=1, max_length=MAX_BARS)
        values: list[float] = Field(min_length=1, max_length=MAX_BARS)
        scale: Scale = "auto"  # bar height scale; auto switches to sqrt/log for huge ranges

        @model_validator(mode="after")
        def _check(self):
            if len(self.labels) != len(self.values):
                raise ValueError(f"labels ({len(self.labels)}) and values ({len(self.values)}) must have the same length")
            if any((not math.isfinite(v)) or v < 0 for v in self.values):
                raise ValueError("values must be finite numbers >= 0")
            if any(len(lab) > MAX_TEXT for lab in self.labels):
                raise ValueError(f"labels must be at most {MAX_TEXT} characters")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.3 * len(p.values)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        return "\n".join([p.title] + [f"{a}: {b:g}" for a, b in zip(p.labels, p.values)])  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, RIGHT, UP, FadeIn, GrowFromEdge, LaggedStart, Line, Rectangle, Text, VGroup, config
        prepare(scene, colors)
        n = len(p.values)
        total = self.duration(p)
        slot = 11.0 / n
        width = min(1.4, slot * 0.7)
        top = max(p.values) or 1.0
        xs = [(-5.5 + slot * (i + 0.5)) for i in range(n)]
        heights, used_scale = scaled_heights(list(p.values), MAX_BAR_HEIGHT, 0.12, p.scale)
        bars, vals, cats = [], [], []
        for i, (lab, v) in enumerate(zip(p.labels, p.values)):
            h = heights[i]
            bar = Rectangle(width=width, height=h, stroke_width=0, fill_opacity=1.0,
                            fill_color=colors.accent if i % 2 == 0 else colors.accent2)
            bar.move_to([xs[i], BASELINE_Y + h / 2, 0])
            val = Text(f"{v:g}", font_size=MIN_FONT_SIZE, color=colors.text).next_to(bar, UP, buff=0.12)
            cat = Text(lab, font_size=MIN_FONT_SIZE, color=colors.muted).next_to(
                Line([xs[i], BASELINE_Y, 0], [xs[i], BASELINE_Y, 0]), DOWN, buff=0.15)
            if cat.width > slot * 0.9:  # crowded: tilt instead of shrinking below the minimum size
                cat.rotate(0.6)
                cat.next_to([xs[i], BASELINE_Y, 0], DOWN, buff=0.1)
            bars.append(bar), vals.append(val), cats.append(cat)
        title = Text(p.title, font_size=MIN_FONT_SIZE + 8, color=colors.text).to_edge(UP, buff=0.55)
        base = Line([-5.6, BASELINE_Y, 0], [5.6, BASELINE_Y, 0], color=colors.muted, stroke_width=3)
        fit(title, max_width=config.frame_width - 2.0, scale_up=False)
        extra = []
        if used_scale in NOTES:
            note = Text(f"({NOTES[used_scale]})", font_size=22, color=colors.muted)
            note.next_to(VGroup(*cats), DOWN, buff=0.15).align_to(base, RIGHT)
            extra = [note]

        # Keep the whole chart, labels and scale note included, above the real
        # caption: its height depends on how the caption wraps, so the room is
        # measured from the caption itself rather than from a fixed baseline.
        chart = VGroup(base, *bars, *vals, *cats, *extra)
        band = caption_band_top_of(getattr(scene, "caption_mobject", None))
        room_top = title.get_bottom()[1] - 0.15
        if chart.height > room_top - band:
            chart.scale((room_top - band) / chart.height)
        if chart.get_bottom()[1] < band:
            chart.shift(UP * (band - chart.get_bottom()[1]))
        clock = Clock(scene, total)
        clock.play(FadeIn(title), FadeIn(base), *[FadeIn(e) for e in extra], *[FadeIn(c) for c in cats], run_time=0.6)
        clock.play(LaggedStart(*[GrowFromEdge(b, DOWN) for b in bars], lag_ratio=0.25),
                   run_time=0.3 * n + 0.6)
        clock.play(*[FadeIn(v) for v in vals], run_time=0.4)
        clock.finish()


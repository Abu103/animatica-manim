"""Number line: a horizontal line with ticks, and arrows jumping between marks.

Made for prompts like "show 3 jumping to 7 on a number line". Duration: 2.0 s + 0.7 s per jump.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_MARKS = 12
MAX_JUMPS = 8


class NumberLine(Component):
    name: ClassVar[str] = "number_line"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        start: float
        end: float
        marks: list[float] = Field(default_factory=list, max_length=MAX_MARKS)
        jumps: list[tuple[float, float]] = Field(default_factory=list, max_length=MAX_JUMPS)

        @model_validator(mode="after")
        def _check(self):
            if self.end <= self.start:
                raise ValueError("end must be greater than start")
            for m in self.marks:
                if not (self.start <= m <= self.end):
                    raise ValueError(f"mark {m} outside [{self.start}, {self.end}]")
            for a, b in self.jumps:
                if not (self.start <= a <= self.end and self.start <= b <= self.end):
                    raise ValueError(f"jump ({a}, {b}) outside [{self.start}, {self.end}]")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.7 * len(p.jumps)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        jumps = ", ".join(f"{a} -> {b}" for a, b in p.jumps)  # type: ignore[attr-defined]
        return f"{p.title}: {p.start} to {p.end}" + (f"; jumps: {jumps}" if jumps else "")  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, UP, FadeIn, FadeOut, Line, Text, VGroup, config

        prepare(scene, colors)
        span = p.end - p.start  # type: ignore[operator]
        x0, x1 = -5.5, 5.5

        def x_of(v: float) -> float:
            return x0 + (v - p.start) / span * (x1 - x0)  # type: ignore[operator]

        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        title.to_edge(UP, buff=0.55)
        line = Line([x0, 0, 0], [x1, 0, 0], color=colors.muted)
        marks = VGroup(line)
        for m in sorted({p.start, p.end, *p.marks}):  # type: ignore[attr-defined]
            tick = Line([x_of(m), -0.12, 0], [x_of(m), 0.12, 0], color=colors.text)
            label = Text(f"{m:g}", font_size=MIN_FONT_SIZE, color=colors.muted)
            label.move_to([x_of(m), -0.55, 0])
            marks.add(tick, label)
        group = VGroup(title, marks)
        fit(group, max_width=config.frame_width - 2.0, scale_up=False)
        group.shift(DOWN * 0.4)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        clock.play(FadeIn(marks), run_time=0.9)
        for a, b in p.jumps:  # type: ignore[attr-defined]
            arrow = Text(f"{a:g} -> {b:g}", font_size=MIN_FONT_SIZE, color=colors.accent)
            arrow.move_to([(x_of(a) + x_of(b)) / 2, 0.9, 0])
            clock.play(FadeIn(arrow), run_time=0.35)
            clock.play(FadeOut(arrow), run_time=0.35)
        clock.finish()

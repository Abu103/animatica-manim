"""Timeline: dots on a horizontal line, labels alternating above/below. Max 8 events.

Duration: 2.0 s + 0.8 s per event.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_EVENTS = 8


class Timeline(Component):
    name: ClassVar[str] = "timeline"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        events: list[dict] = Field(min_length=1, max_length=MAX_EVENTS)

        def model_post_init(self, __context) -> None:
            for i, ev in enumerate(self.events):
                if not ev.get("label") or not ev.get("text"):
                    raise ValueError(f"event {i}: needs both 'label' and 'text'")

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.8 * len(p.events)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [f"{ev['label']}: {ev['text']}" for ev in p.events]  # type: ignore[attr-defined]
        return p.title + ":\n" + "\n".join(lines)  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, UP, FadeIn, Line, Text, VGroup

        prepare(scene, colors)
        n = len(p.events)  # type: ignore[attr-defined]
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        line = Line([-5.5, 0, 0], [5.5, 0, 0], color=colors.muted)
        marks = VGroup(line)
        for i, ev in enumerate(p.events):  # type: ignore[attr-defined]
            x = -5.5 + (i + 0.5) / n * 11.0
            dot = Text("•", font_size=MIN_FONT_SIZE + 10, color=colors.accent).move_to([x, 0, 0])
            lab = Text(wrap(str(ev["label"]), 14), font_size=MIN_FONT_SIZE, color=colors.accent)
            txt = Text(wrap(str(ev["text"]), 22), font_size=MIN_FONT_SIZE - 4, color=colors.text)
            above = i % 2 == 0
            lab.move_to([x, 0.5 if above else -0.5, 0])
            txt.next_to(lab, DOWN if above else UP, buff=0.15) if hasattr(txt, "next_to") else None
            marks.add(dot, lab, txt)
        group = VGroup(title, marks)
        fit(group)
        group.shift(DOWN * 0.3)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        clock.play(FadeIn(line), run_time=0.6)
        for i in range(2, len(marks)):
            clock.play(FadeIn(marks[i]), run_time=0.8)
        clock.finish()

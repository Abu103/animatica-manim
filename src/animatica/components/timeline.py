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
        from manim import DOWN, UP, FadeIn, Line, Text, VGroup, config

        prepare(scene, colors)
        n = len(p.events)  # type: ignore[attr-defined]
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        title.to_edge(UP, buff=0.55)
        line = Line([-5.5, 0, 0], [5.5, 0, 0], color=colors.muted)
        marks = VGroup(line)
        events: list = []
        for i, ev in enumerate(p.events):  # type: ignore[attr-defined]
            x = -5.5 + (i + 0.5) / n * 11.0
            dot = Text("•", font_size=MIN_FONT_SIZE + 10, color=colors.accent).move_to([x, 0, 0])
            lab = Text(wrap(str(ev["label"]), 14), font_size=MIN_FONT_SIZE, color=colors.accent)
            txt = Text(wrap(str(ev["text"]), 22), font_size=MIN_FONT_SIZE - 4, color=colors.text)
            above = i % 2 == 0
            lab.move_to([x, 0.55 if above else -0.55, 0])
            # The description goes away from the axis. Pointing it at the axis
            # put it straight on top of the line and of the event's own dot.
            txt.next_to(lab, UP if above else DOWN, buff=0.15)
            event = VGroup(dot, lab, txt)
            marks.add(event)
            events.append(event)
        group = VGroup(marks)
        # Shrink only: scaling the timeline up to fill the frame pushed the
        # axis past the safe-area margin frame-lint keeps free.
        fit(group, max_width=config.frame_width - 1.6, scale_up=False)
        group.shift(UP * 0.3)
        clock = Clock(scene, self.duration(p))
        # One fade per event, so the beat uses exactly the time it declared:
        # 0.8 + 0.8 + 0.8 per event + the 0.4s fade-out is 2.0 + 0.8 per event.
        clock.play(FadeIn(title), run_time=0.8)
        clock.play(FadeIn(line), run_time=0.8)
        for event in events:
            clock.play(FadeIn(event), run_time=0.8)
        clock.finish()

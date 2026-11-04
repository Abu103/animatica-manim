"""Title card: title with optional subtitle, fades in and out. 3.0 s."""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT


class TitleCard(Component):
    name: ClassVar[str] = "title_card"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        subtitle: str = Field("", max_length=MAX_TEXT)

    def duration(self, p: BaseModel) -> float:
        return 3.0

    def fallback_text(self, p: BaseModel) -> str:
        return p.title  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, Text, VGroup
        prepare(scene, colors)
        title = Text(wrap(p.title, 30), font_size=MIN_FONT_SIZE + 24, color=colors.text, weight="BOLD")
        group = VGroup(title)
        if p.subtitle:
            group.add(Text(wrap(p.subtitle, 50), font_size=MIN_FONT_SIZE, color=colors.muted))
        group.arrange(DOWN, buff=0.5)
        fit(group)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(group, shift=0.3 * DOWN), run_time=1.0)
        clock.finish()


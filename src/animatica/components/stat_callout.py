"""Stat callout: a large headline number with a supporting label.

Made for prompts like "show the key statistic" or "highlight this number".
Displays a big value with a smaller caption underneath, optionally with a
comparison delta (e.g. "+12% vs last year").
Duration: 3.0 s fixed.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from animatica.components._draw import Clock, fit, fit_in_room, prepare
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT


class StatCallout(Component):
    name: ClassVar[str] = "stat_callout"

    class Params(BaseModel):
        value: str = Field(max_length=MAX_TEXT, description="headline number/statistic")
        label: str = Field(max_length=MAX_TEXT, description="what the number means")
        delta: str = Field(
            default="",
            max_length=MAX_TEXT,
            description="optional comparison, e.g. '+12% vs last year'",
        )

    def duration(self, p: BaseModel) -> float:
        return 3.0

    def fallback_text(self, p: BaseModel) -> str:
        parts = [f"{p.value} — {p.label}"]
        if p.delta:
            parts.append(f"({p.delta})")
        return " ".join(parts)

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, Text, VGroup

        prepare(scene, colors)
        big = Text(p.value, font_size=72, color=colors.text)
        fit(big)
        label = Text(p.label, font_size=32, color=colors.muted)
        if label.width > 11.0:
            label.scale_to_fit_width(11.0)
        group = VGroup(big, label).arrange(DOWN, buff=0.4)
        if p.delta:
            delta = Text(p.delta, font_size=28, color=colors.accent2)
            if delta.width > 11.0:
                delta.scale_to_fit_width(11.0)
            group = VGroup(group, delta).arrange(DOWN, buff=0.3)
        fit_in_room(scene, group)

        clock = Clock(scene, 3.0)
        clock.play(FadeIn(big), run_time=0.8)
        clock.play(FadeIn(label), run_time=0.6)
        if p.delta:
            clock.play(FadeIn(delta), run_time=0.6)
        clock.finish()

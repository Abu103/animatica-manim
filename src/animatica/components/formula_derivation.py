"""Formula derivation: step-by-step math derivation with highlighted transitions.

Made for prompts like "derive the quadratic formula" or "show how to solve
for x step by step". Each line is an equation; arrows or highlights show
the transition from one step to the next.
Duration: 2.0 s + 1.0 s per step.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import SAFE_AREA_MARGIN, Clock, fit, prepare, text_card, warn
from animatica.components._draw import caption_band_top as caption_band_top_of
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_STEPS = 6


class FormulaDerivation(Component):
    name: ClassVar[str] = "formula_derivation"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        steps: list[str] = Field(min_length=1, max_length=MAX_STEPS)
        highlight: list[int] = Field(
            default_factory=list,
            description="step indices to highlight (0-based)",
        )

        @model_validator(mode="after")
        def _check_highlight(self) -> "FormulaDerivation.Params":
            n = len(self.steps)
            for i in self.highlight:
                if not (0 <= i < n):
                    raise ValueError(
                        f"highlight index {i} out of range for {n} steps"
                    )
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 1.0 * len(p.steps)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [f"{p.title}"] + [f"{i + 1}. {s}" for i, s in enumerate(p.steps)]  # type: ignore[attr-defined]
        return "\n".join(lines)

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, Text, UP, VGroup

        prepare(scene, colors)
        steps = p.steps  # type: ignore[attr-defined]
        highlight = set(p.highlight)  # type: ignore[attr-defined]
        n = len(steps)

        # The title and the steps live in the space between the top margin and the
        # caption (#29). A two-line caption is taller than a one-line one, so the room
        # is measured from the real caption, not assumed.
        from manim import config

        top = config.frame_height * (0.5 - SAFE_AREA_MARGIN) - 0.3
        band = caption_band_top_of(getattr(scene, "caption_mobject", None))
        max_width = config.frame_width * (1 - 2 * SAFE_AREA_MARGIN) - 0.3
        gap = 0.4

        title = Text(p.title, font_size=40, color=colors.text)
        fit(title, max_width=max_width, max_height=1.0, scale_up=False)

        rendered: list = []
        for i, step in enumerate(steps):
            line = Text(f"{i + 1}. {step}", font_size=36,
                        color=colors.accent if i in highlight else colors.text)
            rendered.append(line)

        group = VGroup(*rendered).arrange(DOWN, buff=0.5)
        fit(group, max_width=max_width, max_height=top - band - title.height - gap)
        whole = VGroup(title, group).arrange(DOWN, buff=gap)
        whole.move_to([0.0, (top + band) / 2, 0.0])
        title.set_x(0.0)
        group.set_x(0.0)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        per = max(0.3, 1.8 / n)
        for line in rendered:
            clock.play(FadeIn(line), run_time=per)
        clock.finish()

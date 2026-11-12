"""Steps list: items revealed one by one, current item highlighted. 1.5 s per item + 1.0 s."""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components._draw import SAFE_AREA_MARGIN
from animatica.components._draw import caption_band_top as caption_band_top_of
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT


class StepsList(Component):
    name: ClassVar[str] = "steps_list"

    class Params(BaseModel):
        items: list[str] = Field(min_length=1, max_length=8)

    def duration(self, p: BaseModel) -> float:
        return 1.5 * len(p.items) + 1.0  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        return "\n".join(p.items)  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, LEFT, FadeIn, Text, VGroup
        prepare(scene, colors)
        rows = VGroup(*[
            Text(f"{i}. {wrap(item[:MAX_TEXT], 45)}", font_size=MIN_FONT_SIZE + 4, color=colors.muted)
            for i, item in enumerate(p.items, 1)
        ]).arrange(DOWN, aligned_edge=LEFT, buff=0.45)
        # The rows live in the space between the top margin and the caption (#30):
        # a two-line caption is taller than a one-line one, so the room is measured
        # from the real caption, not assumed.
        from manim import config
        top = config.frame_height * (0.5 - SAFE_AREA_MARGIN) - 0.3
        band = caption_band_top_of(getattr(scene, "caption_mobject", None))
        fit(rows, max_width=config.frame_width * (1 - 2 * SAFE_AREA_MARGIN) - 0.3, max_height=top - band)
        rows.move_to([0.0, (top + band) / 2, 0.0])
        clock = Clock(scene, self.duration(p))
        shown = VGroup()
        for row in rows:
            row.set_color(colors.accent)
            for earlier in shown:
                earlier.set_color(colors.muted)
            shown.add(row)
            clock.play(FadeIn(row, shift=0.2 * DOWN), run_time=0.6)
            clock.wait(0.9)
        clock.finish()


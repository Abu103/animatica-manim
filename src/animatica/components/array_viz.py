"""Array viz: boxes with values; steps highlight indices or swap pairs (sort/search demos).

Duration: 2.0 s + 0.8 s per step.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_VALUES = 12


class ArrayViz(Component):
    name: ClassVar[str] = "array_viz"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        values: list[float] = Field(min_length=2, max_length=MAX_VALUES)
        steps: list[dict] = Field(default_factory=list, max_length=12)

        @model_validator(mode="after")
        def _check(self):
            n = len(self.values)
            for i, st in enumerate(self.steps):
                for key in ("highlight", "swap"):
                    if key not in st:
                        continue
                    idxs = st.get(key) or []
                    if key == "swap" and len(idxs) != 2:
                        raise ValueError(f"step {i}: swap needs exactly 2 indices")
                    for ix in idxs:
                        if not (0 <= ix < n):
                            raise ValueError(f"step {i}: index {ix} out of range for {n} values")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.8 * len(p.steps)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        return f"{p.title}: [{', '.join(f'{v:g}' for v in p.values)}]"  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import FadeIn, Text, VGroup

        prepare(scene, colors)
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        boxes = VGroup(*[
            Text(f"{v:g}", font_size=MIN_FONT_SIZE + 4, color=colors.text) for v in p.values  # type: ignore[attr-defined]
        ]).arrange_in_grid(1, len(p.values), buff=0.9)  # type: ignore[attr-defined]
        group = VGroup(title, boxes)
        fit(group)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        clock.play(FadeIn(boxes), run_time=0.9)
        for st in p.steps:  # type: ignore[attr-defined]
            for ix in st.get("highlight") or []:
                boxes[ix].set_color(colors.accent)
                clock.play(FadeIn(boxes[ix]), run_time=0.4)
                boxes[ix].set_color(colors.text)
            sw = st.get("swap") or []
            if len(sw) == 2:
                i, j = sw
                clock.play(boxes[i].animate.move_to(boxes[j].get_center()), run_time=0.4)
                clock.play(boxes[j].animate.move_to(boxes[i].get_center()), run_time=0.4)
                boxes[i], boxes[j] = boxes[j], boxes[i]
            clock.wait(0.0)
        clock.finish()

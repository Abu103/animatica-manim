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

Point = tuple[float, float, float]


def swap_targets(centers: list[Point], i: int, j: int) -> list[tuple[int, Point]]:
    """Move targets for swapping slots ``i`` and ``j``, read from the ORIGINAL
    centers so both boxes move simultaneously to each other's slot.
    Returns ``[]`` when ``i == j`` (a same-index swap is a no-op)."""
    if i == j:
        return []
    return [(i, centers[j]), (j, centers[i])]


def opacity_for(ix: int, low: int | None, high: int | None) -> float:
    """Opacity for box ``ix`` given the active ``low``/``high`` range.
    Full (1.0) inside the range or when no range is set; dimmed (0.25) outside."""
    if low is None and high is None:
        return 1.0
    if low is not None and ix < low:
        return 0.25
    if high is not None and ix > high:
        return 0.25
    return 1.0


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
                for key in ("low", "high", "mid"):
                    if key in st:
                        ix = st[key]
                        if type(ix) is not int or not (0 <= ix < n):
                            raise ValueError(f"step {i}: {key} must be an integer index in [0, {n - 1}]")
                lo, hi, mid = st.get("low"), st.get("high"), st.get("mid")
                if lo is not None and hi is not None and lo > hi:
                    raise ValueError(f"step {i}: low must not exceed high")
                if mid is not None and ((lo is not None and mid < lo) or (hi is not None and mid > hi)):
                    raise ValueError(f"step {i}: mid must lie within the active range")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.8 * len(p.steps)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        return f"{p.title}: [{', '.join(f'{v:g}' for v in p.values)}]"  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, Text, VGroup

        prepare(scene, colors)
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        boxes = VGroup(*[
            Text(f"{v:g}", font_size=MIN_FONT_SIZE + 4, color=colors.text) for v in p.values  # type: ignore[attr-defined]
        ]).arrange_in_grid(1, len(p.values), buff=0.9)  # type: ignore[attr-defined]
        group = VGroup(title, boxes).arrange(DOWN, buff=0.5)
        fit(group)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        clock.play(FadeIn(boxes), run_time=0.9)
        for st in p.steps:  # type: ignore[attr-defined]
            centers = [tuple(b.get_center()) for b in boxes]
            sw = st.get("swap") or []
            if len(sw) == 2:
                i, j = sw
                clock.play(
                    *[boxes[k].animate.move_to(pt) for k, pt in swap_targets(centers, i, j)],
                    run_time=0.8,
                )
                boxes[i], boxes[j] = boxes[j], boxes[i]
                clock.wait(0.0)
                continue
            low, high, mid = st.get("low"), st.get("high"), st.get("mid")
            if low is not None or high is not None:
                n = len(boxes)
                for ix in range(n):
                    clock.play(
                        boxes[ix].animate.set_opacity(opacity_for(ix, low, high)),
                        run_time=0.8 / n,
                    )
            if mid is not None:
                boxes[mid].set_color(colors.accent)
                clock.play(FadeIn(boxes[mid]), run_time=0.8)
                boxes[mid].set_color(colors.text)
            for ix in st.get("highlight") or []:
                boxes[ix].set_color(colors.accent)
                idxs = st.get("highlight") or []
                clock.play(FadeIn(boxes[ix]), run_time=0.8 / max(1, len(idxs)))
                boxes[ix].set_color(colors.text)
            clock.wait(0.0)
        clock.finish()

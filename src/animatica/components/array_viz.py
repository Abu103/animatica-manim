"""Array viz: boxes with values; steps highlight indices or swap pairs (sort/search demos).

Duration: 2.0 s + 0.8 s per step. The animations are carved out of that
budget in whole video frames (the fade-out at the end included), so the beat
takes exactly the duration it declares.
"""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import FADE_OUT, MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components._draw import caption_band_top as caption_band_top_of
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT
from animatica.verify.facts import Fact, format_number

MAX_VALUES = 12

Point = tuple[float, float, float]


def _data(p: BaseModel) -> tuple[list[float], list[float]]:
    """The initial values play() draws, and the final state after the steps.

    Only steps that carry ``swap`` change the array (``i == j`` is a no-op,
    exactly as ``swap_targets`` treats it); ``highlight``/``low``/``high``/
    ``mid`` steps only change the drawing.
    """
    final = list(p.values)  # type: ignore[attr-defined]
    for st in p.steps:  # type: ignore[attr-defined]
        sw = st.get("swap") or []
        if len(sw) == 2 and sw[0] != sw[1]:
            i, j = sw
            final[i], final[j] = final[j], final[i]
    return list(p.values), final  # type: ignore[attr-defined]


def _number_text(v: float) -> str:
    """How a fact text writes a box value: ``inf`` is spelled out."""
    if math.isinf(v):
        return "negative infinity" if v < 0 else "infinity"
    return format_number(v)


def value_label(v: float) -> str:
    """The text drawn in a box. ``inf`` is drawn as ``∞`` (distance arrays start at infinity)."""
    if math.isinf(v):
        return "∞" if v > 0 else "-∞"
    return f"{v:g}"


def swap_targets(centers: list[Point], i: int, j: int) -> list[tuple[int, Point]]:
    """Move targets for swapping slots ``i`` and ``j``, read from the ORIGINAL
    centers so both boxes move simultaneously to each other's slot.
    Returns ``[]`` when ``i == j`` (a same-index swap is a no-op)."""
    if i == j:
        return []
    return [(i, centers[j]), (j, centers[i])]


def split_frames(total: int, parts: int) -> list[int]:
    """`total` frames shared between `parts` animations: every part gets at
    least one frame, the shares add up to `total` (when it allows) and the
    earlier parts take the remainder."""
    if parts <= 0:
        return []
    base, extra = divmod(max(total, parts), parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


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
    domain: ClassVar[str] = "plain axes"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        values: list[float] = Field(min_length=2, max_length=MAX_VALUES)
        steps: list[dict] = Field(default_factory=list, max_length=12)

        @model_validator(mode="after")
        def _check(self):
            n = len(self.values)
            if any(math.isnan(v) for v in self.values):
                raise ValueError("values must not contain nan (use \"inf\" for infinity)")
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
        return f"{p.title}: [{', '.join(value_label(v) for v in p.values)}]"  # type: ignore[attr-defined]

    def facts(self, p: BaseModel) -> list[Fact]:
        _, final = _data(p)
        swaps = sum(
            1 for st in p.steps  # type: ignore[attr-defined]
            if len(st.get("swap") or []) == 2 and st["swap"][0] != st["swap"][1]
        )
        sorted_ok = all(a <= b for a, b in zip(final, final[1:]))
        facts = [
            Fact("sorted", "final_state", sorted_ok,
                 "the array is sorted in ascending order at the end" if sorted_ok
                 else "the array is not sorted in ascending order at the end"),
            Fact("swaps", "steps", swaps,
                 f"the steps swap two boxes {swaps} times"),
            Fact("value", "final_state", tuple(final),
                 "final order is [" + ", ".join(_number_text(v) for v in final) + "]"),
        ]
        for word, val in (("largest", max(final)), ("smallest", min(final))):
            ix = final.index(val)  # first occurrence: the first box with that value
            facts.append(Fact("extremum", "final_state", (ix, val),
                              f"{word} value is {_number_text(val)} at position {ix}"
                              " (position 0 is the first box)"))
        return facts

    def play(self, scene, p, colors) -> None:
        from manim import UP, FadeIn, Text, VGroup, config

        prepare(scene, colors)
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        # The title sits at the top of the frame, centred. It used to keep
        # the place the layout gave it, which left the whole top of the
        # frame empty.
        title.to_edge(UP, buff=0.6).set_x(0)
        initial, _ = _data(p)
        boxes = VGroup(*[
            Text(value_label(v), font_size=MIN_FONT_SIZE + 4, color=colors.text) for v in initial
        ]).arrange_in_grid(1, len(initial), buff=0.9)
        # The boxes fill the stage. The cap keeps them inside the safe area:
        # at most 70% of the frame width.
        fit(boxes, max_width=config.frame_width * 0.7, max_height=config.frame_height - 2.4, scale_up=True)
        # The boxes are centred in the space below the title, above the
        # caption.
        band = caption_band_top_of(getattr(scene, "caption_mobject", None))
        boxes.move_to([0.0, (title.get_bottom()[1] - 0.5 + band) / 2, 0.0])
        clock = Clock(scene, self.duration(p))
        # The budget: the whole beat minus the fade-out, in whole frames. The
        # intro takes 1.6 s of it (the 2.0 s the formula gives a step-less
        # array, minus the fade) and every step shares the rest equally.
        total_f = clock.frames(self.duration(p) - FADE_OUT)
        intro_f = min(clock.frames(2.0 - FADE_OUT), total_f)
        title_f = max(1, round(intro_f * 0.375))
        boxes_f = max(1, intro_f - title_f)
        clock.play(FadeIn(title), run_time=clock.seconds(title_f))
        clock.play(FadeIn(boxes), run_time=clock.seconds(boxes_f))
        steps = p.steps  # type: ignore[attr-defined]
        step_frames = split_frames(total_f - intro_f, len(steps))
        for st, step_f in zip(steps, step_frames):
            centers = [tuple(b.get_center()) for b in boxes]
            sw = st.get("swap") or []
            if len(sw) == 2:
                i, j = sw
                clock.play(
                    *[boxes[k].animate.move_to(pt) for k, pt in swap_targets(centers, i, j)],
                    run_time=clock.seconds(step_f),
                )
                boxes[i], boxes[j] = boxes[j], boxes[i]
                clock.wait(0.0)
                continue
            low, high, mid = st.get("low"), st.get("high"), st.get("mid")
            highlights = st.get("highlight") or []
            # One animation per kind of change, all inside this step's frames.
            # The boxes of a range change fade together, the highlighted ones
            # light up together.
            parts = [bool(low is not None or high is not None), mid is not None, bool(highlights)]
            shares = iter(split_frames(step_f, sum(parts)))
            if parts[0]:
                n = len(boxes)
                clock.play(
                    *[boxes[ix].animate.set_opacity(opacity_for(ix, low, high)) for ix in range(n)],
                    run_time=clock.seconds(next(shares)),
                )
            if parts[1]:
                boxes[mid].set_color(colors.accent)
                clock.play(FadeIn(boxes[mid]), run_time=clock.seconds(next(shares)))
                boxes[mid].set_color(colors.text)
            if parts[2]:
                for ix in highlights:
                    boxes[ix].set_color(colors.accent)
                clock.play(*[FadeIn(boxes[ix]) for ix in highlights], run_time=clock.seconds(next(shares)))
                for ix in highlights:
                    boxes[ix].set_color(colors.text)
            if not any(parts):  # an empty step still takes its time
                clock.wait(clock.seconds(step_f))
            clock.wait(0.0)
        clock.finish()

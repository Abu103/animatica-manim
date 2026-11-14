"""Bounce sequence: a ball hops along a number sequence, building one pad per term.

Made for prompts like "explain Fibonacci with a ball bouncing on each term". Each pad's
height is its value; when the ball lands the pad grows and its value appears. If a term is
the sum of the two before it (Fibonacci-like), the sum is shown too: "3 + 5 = 8".
Duration: 2.0 s + 0.8 s per term.
"""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, caption_band_top, fit, prepare
from animatica.components._scale import NOTES, Scale, scaled_heights
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_TERMS = 20
BASELINE_Y = -1.9
MAX_PAD_HEIGHT = 3.0
MIN_PAD_HEIGHT = 0.12
X_SPAN = 11.6
HOP_TIME = 0.5
LAND_TIME = 0.3


def sum_rule_holds(values: list[float], i: int) -> bool:
    """True if values[i] == values[i-1] + values[i-2] (needs i >= 2 and a non-trivial sum)."""
    return i >= 2 and math.isclose(values[i], values[i - 1] + values[i - 2], abs_tol=1e-9) and values[i] > 0


def parabola_point(start: tuple[float, float], end: tuple[float, float], t: float, lift: float) -> tuple[float, float]:
    """Point at progress t (0..1) on a hop from start to end, bulging `lift` above the straight line."""
    x = start[0] + (end[0] - start[0]) * t
    y = start[1] + (end[1] - start[1]) * t + 4.0 * t * (1.0 - t) * lift
    return x, y


class BounceSequence(Component):
    name: ClassVar[str] = "bounce_sequence"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        values: list[float] = Field(min_length=2, max_length=MAX_TERMS)
        labels: list[str] = Field(default_factory=list, max_length=MAX_TERMS)  # default: term numbers 0, 1, 2...
        scale: Scale = "auto"  # pad height scale; auto switches to sqrt/log when values span a huge range

        @model_validator(mode="after")
        def _check(self):
            if any((not math.isfinite(v)) or v < 0 for v in self.values):
                raise ValueError("values must be finite numbers >= 0")
            if self.labels and len(self.labels) != len(self.values):
                raise ValueError(f"labels ({len(self.labels)}) and values ({len(self.values)}) must have the same length")
            if any(len(x) > 12 for x in self.labels):
                raise ValueError("labels must be at most 12 characters (they sit under each pad)")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.8 * len(p.values)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        vals = ", ".join(f"{v:g}" for v in p.values)  # type: ignore[attr-defined]
        return f"{p.title}\n{vals}"  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import (DOWN, LEFT, UP, Dot, FadeIn, FadeOut, GrowFromEdge, Line, Rectangle, Text,
                           UpdateFromAlphaFunc, config)
        prepare(scene, colors)
        values = list(p.values)
        n = len(values)
        total = self.duration(p)
        labels = p.labels or [str(i) for i in range(n)]
        slot = X_SPAN / n
        pad_w = min(0.95, slot * 0.62)
        xs = [-X_SPAN / 2 + slot * (i + 0.5) for i in range(n)]
        _, used_scale = scaled_heights(values, MAX_PAD_HEIGHT, MIN_PAD_HEIGHT, p.scale)
        radius = 0.2

        title = Text(p.title, font_size=40, color=colors.text).to_edge(UP, buff=0.55)
        fit(title, max_width=config.frame_width - 2.0, scale_up=False)
        base = Line([-X_SPAN / 2 - 0.2, BASELINE_Y, 0], [X_SPAN / 2 + 0.2, BASELINE_Y, 0],
                    color=colors.muted, stroke_width=3)
        label_size = 30 if n <= 8 else 26 if n <= 14 else 22
        cats = []
        for i, lab in enumerate(labels):
            t = Text(lab, font_size=label_size, color=colors.muted)
            if t.width > slot * 0.9:
                t.scale_to_fit_width(slot * 0.9)
            cats.append(t.move_to([xs[i], BASELINE_Y - 0.4, 0]))
        note = (("term" if not p.labels else "") + ("   " if not p.labels and used_scale in NOTES else "")
                + (f"({NOTES[used_scale]})" if used_scale in NOTES else "")).strip()
        axis_note = Text(note, font_size=22, color=colors.muted).next_to(base, DOWN, buff=0.85).align_to(base, LEFT) \
            if note else None

        # Leave the caption its room (#33): the labels and the note hang below the
        # baseline, so the baseline must sit high enough for the lowest of them to
        # clear the caption band. The pads give up the same height, so the top of
        # the stage (ball, sum text) stays where it was.
        band = caption_band_top(getattr(scene, "caption_mobject", None))
        lowest = min(m.get_bottom()[1] for m in [*cats, *([axis_note] if axis_note is not None else [])])
        lift_stage = max(0.0, band - lowest)
        base_y = BASELINE_Y + lift_stage
        for m in (base, *cats, *([axis_note] if axis_note is not None else [])):
            m.shift(UP * lift_stage)
        heights, _ = scaled_heights(values, MAX_PAD_HEIGHT - lift_stage, MIN_PAD_HEIGHT, p.scale)
        tops = [base_y + h for h in heights]

        pads, vals = [], []
        for i in range(n):
            pad = Rectangle(width=pad_w, height=heights[i], stroke_width=0, fill_opacity=1.0,
                            fill_color=colors.accent if i % 2 == 0 else colors.accent2)
            pad.move_to([xs[i], base_y + heights[i] / 2, 0])
            pads.append(pad)
            vals.append(Text(f"{values[i]:g}", font_size=label_size + 4, color=colors.text)
                        .next_to(pad, UP, buff=0.12))

        ball = Dot(radius=radius, color=colors.text)
        ball.set_fill(colors.text, opacity=1.0)

        def rest_pos(i: int) -> tuple[float, float]:
            # Resting on the pad, but above the value label so the two never overlap.
            return xs[i], tops[i] + radius + 0.55

        clock = Clock(scene, total)
        intro = [FadeIn(title), FadeIn(base), *[FadeIn(c) for c in cats]]
        if axis_note is not None:
            intro.append(FadeIn(axis_note))
        clock.play(*intro, run_time=0.6)

        # Landing on term 0: ball drops in, first pad grows.
        sx, sy = rest_pos(0)
        ball.move_to([sx, sy + 1.2, 0])
        scene.add(ball)
        clock.play(
            UpdateFromAlphaFunc(ball, lambda m, a, sx=sx, sy=sy: m.move_to([sx, sy + 1.2 * (1 - a), 0])),
            GrowFromEdge(pads[0], DOWN), FadeIn(vals[0]), run_time=0.5,
        )

        sum_text = None
        for i in range(1, n):
            start, end = rest_pos(i - 1), rest_pos(i)
            lift = 0.7 + 0.35 * abs(end[1] - start[1])

            def hop(m, a, start=start, end=end, lift=lift):
                x, y = parabola_point(start, end, a, lift)
                m.move_to([x, y, 0])

            clock.play(UpdateFromAlphaFunc(ball, hop), run_time=HOP_TIME)
            landing = [GrowFromEdge(pads[i], DOWN), FadeIn(vals[i])]
            if sum_rule_holds(values, i):
                new_sum = Text(f"{values[i - 2]:g} + {values[i - 1]:g} = {values[i]:g}",
                               font_size=44, color=colors.accent2).move_to([0, 2.4, 0])
                if sum_text is not None:
                    landing.append(FadeOut(sum_text))
                landing.append(FadeIn(new_sum))
                sum_text = new_sum
            clock.play(*landing, run_time=LAND_TIME)
        clock.finish()


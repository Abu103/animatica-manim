"""Parametric graph: plots x(t), y(t) curves over a parameter range.

Made for prompts like "graph a parametric circle" or "show a Lissajous curve".
Takes x(t) and y(t) expressions plus a t range, plots the traced curve.
Duration: 4.0 s fixed.
"""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit, prepare, text_card, warn
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT
from animatica.storyboard.safety import parse_function, UnsafeInput

SAMPLES = 400


class ParametricGraph(Component):
    name: ClassVar[str] = "parametric_graph"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        x_expr: str = Field(max_length=MAX_TEXT, description="x as a function of t")
        y_expr: str = Field(max_length=MAX_TEXT, description="y as a function of t")
        t_range: tuple[float, float] = Field(
            default=(0.0, 6.28),
            description="[t_min, t_max] parameter range",
        )
        label: str = Field(default="", max_length=MAX_TEXT)

        @model_validator(mode="after")
        def _check(self):
            # parse_function uses variable `x`; substitute `t` -> `x` for validation
            parse_function(self.x_expr.replace("t", "x"))
            parse_function(self.y_expr.replace("t", "x"))
            lo, hi = self.t_range
            if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
                raise ValueError("t_range must be two finite numbers with min < max")
            return self

    def duration(self, p: BaseModel) -> float:
        return 4.0

    def fallback_text(self, p: BaseModel) -> str:
        return (
            f"{p.title}\nx(t) = {p.x_expr}\ny(t) = {p.y_expr}\n"
            f"t in [{p.t_range[0]}, {p.t_range[1]}]"
        )  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import Axes, Create, DOWN, FadeIn, Text, VGroup, VMobject

        prepare(scene, colors)
        (t0, t1) = p.t_range
        label = p.label

        # Parse expressions (variable `t` -> `x` for the safe parser)
        try:
            fx = parse_function(p.x_expr.replace("t", "x"))
            fy = parse_function(p.y_expr.replace("t", "x"))
        except UnsafeInput as exc:
            warn(scene, f"parametric_graph: unsafe expression ({exc})")
            text_card(scene, self.fallback_text(p), colors, 4.0)
            return

        # Sample x(t), y(t)
        pts = []
        for i in range(SAMPLES):
            t = t0 + (t1 - t0) * i / (SAMPLES - 1)
            try:
                x = fx(t)
                y = fy(t)
            except Exception:
                continue
            if math.isfinite(x) and math.isfinite(y):
                pts.append((x, y))

        if len(pts) < 2:
            warn(scene, "parametric_graph: no valid points; showing text card")
            text_card(scene, self.fallback_text(p), colors, 4.0)
            return

        xs = [pt[0] for pt in pts]
        ys = [pt[1] for pt in pts]
        x_lo, x_hi = min(xs), max(xs)
        y_lo, y_hi = min(ys), max(ys)
        pad = 0.05 * max(x_hi - x_lo, y_hi - y_lo, 1.0)

        try:
            axes = Axes(
                x_range=[x_lo - pad, x_hi + pad, max((x_hi - x_lo) / 5, 0.1)],
                y_range=[y_lo - pad, y_hi + pad, max((y_hi - y_lo) / 5, 0.1)],
                x_length=10.0,
                y_length=5.0,
                axis_config={"color": colors.muted, "include_numbers": True},
            )
        except Exception as exc:  # axes need LaTeX for numbers: degrade
            warn(scene, f"parametric_graph: axes failed ({exc}); showing text card")
            text_card(scene, self.fallback_text(p), colors, 4.0)
            return

        curve = VMobject(stroke_color=colors.accent, stroke_width=6, fill_opacity=0)
        curve.set_points_as_corners([axes.c2p(x, y) for x, y in pts])

        title = Text(p.title, font_size=40, color=colors.text)
        if label:
            label_mob = Text(label, font_size=32, color=colors.muted)
            whole = VGroup(title, axes, curve, label_mob).arrange(DOWN, buff=0.3)
        else:
            whole = VGroup(title, axes, curve).arrange(DOWN, buff=0.3)
        fit(whole)

        clock = Clock(scene, 4.0)
        clock.play(FadeIn(title), run_time=0.8)
        clock.play(FadeIn(axes), run_time=0.8)
        clock.play(Create(curve), run_time=2.0)
        if label:
            clock.play(FadeIn(label), run_time=0.4)
        clock.finish()

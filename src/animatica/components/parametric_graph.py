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
            # parse_function uses variable `t` natively (no string replacement)
            parse_function(self.x_expr, var_name="t")
            parse_function(self.y_expr, var_name="t")
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

        # Parse expressions using variable `t` natively (no string replacement).
        try:
            fx = parse_function(p.x_expr, var_name="t")
            fy = parse_function(p.y_expr, var_name="t")
        except UnsafeInput as exc:
            warn(scene, f"parametric_graph: unsafe expression ({exc})")
            text_card(scene, self.fallback_text(p), colors, 4.0)
            return

        # Sample x(t), y(t), splitting into segments at discontinuities.
        # A discontinuity is detected when consecutive points jump by more
        # than half the axis range in either dimension.
        segments: list[list[tuple[float, float]]] = []
        current_segment: list[tuple[float, float]] = []
        prev_point: tuple[float, float] | None = None

        for i in range(SAMPLES):
            t = t0 + (t1 - t0) * i / (SAMPLES - 1)
            try:
                x = fx(t)
                y = fy(t)
            except Exception:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []
                prev_point = None
                continue
            if math.isfinite(x) and math.isfinite(y):
                point = (x, y)
                if prev_point is not None:
                    dx = abs(x - prev_point[0])
                    dy = abs(y - prev_point[1])
                    # Heuristic: a jump larger than half the eventual range
                    # indicates a discontinuity (e.g. tan(t) near pi/2).
                    # Use a generous threshold so normal steep curves are
                    # not split; only near-vertical jumps are broken.
                    if dx > 1.0 or dy > 1.0:
                        if current_segment:
                            segments.append(current_segment)
                        current_segment = [point]
                    else:
                        current_segment.append(point)
                else:
                    current_segment.append(point)
                prev_point = point
            else:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []
                prev_point = None
        if current_segment:
            segments.append(current_segment)

        # Filter out segments with fewer than 2 points.
        segments = [s for s in segments if len(s) >= 2]

        if not segments:
            warn(scene, "parametric_graph: no valid points; showing text card")
            text_card(scene, self.fallback_text(p), colors, 4.0)
            return

        # Compute axis bounds from all valid points.
        all_pts = [pt for seg in segments for pt in seg]
        xs = [pt[0] for pt in all_pts]
        ys = [pt[1] for pt in all_pts]
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

        # Draw each continuous segment as a separate curve so discontinuities
        # are not connected by misleading lines.
        curves = []
        for seg in segments:
            curve = VMobject(stroke_color=colors.accent, stroke_width=6, fill_opacity=0)
            curve.set_points_as_corners([axes.c2p(x, y) for x, y in seg])
            curves.append(curve)

        title = Text(p.title, font_size=40, color=colors.text)

        # Group axes with all curves so they are positioned as a unit.
        # Curves are defined relative to axes coordinates, so they must move
        # together with the axes when the whole group is arranged/scaled.
        plot_group = VGroup(axes, *curves)

        if label:
            label_mob = Text(label, font_size=32, color=colors.muted)
            whole = VGroup(title, plot_group, label_mob).arrange(DOWN, buff=0.3)
        else:
            whole = VGroup(title, plot_group).arrange(DOWN, buff=0.3)
        fit(whole)

        clock = Clock(scene, 4.0)
        clock.play(FadeIn(title), run_time=0.8)
        clock.play(FadeIn(plot_group), run_time=0.8)
        for curve in curves:
            clock.play(Create(curve), run_time=1.2 / len(curves))
        if label:
            clock.play(FadeIn(label), run_time=0.4)
        clock.finish()

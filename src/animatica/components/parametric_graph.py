"""Parametric graph: plots x(t), y(t) curves over a parameter range.

Made for prompts like "graph a parametric circle" or "show a Lissajous curve".
Takes x(t) and y(t) expressions plus a t range, plots the traced curve.
Duration: 4.0 s fixed.
"""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit_in_room, prepare, text_card, warn
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT
from animatica.storyboard.safety import parse_function, UnsafeInput

SAMPLES = 400


def _nice_axis(lo: float, hi: float) -> tuple[float, float, float]:
    """Round a sampled range to ``(start, stop, step)`` the viewer can read.

    ``lo`` and ``hi`` come from sampling the curve, so they are floats like
    -0.9999900318453959; Manim prints axis numbers straight from the range
    and the step. The step is a "nice" one (1, 2 or 5 times a power of ten,
    the way ``graph`` picks it), and both ends are multiples of it, so every
    tick is a round number. The result always contains ``[lo, hi]``.
    """
    from animatica.components.graph import nice_step

    span = hi - lo
    if span <= 0:  # a constant curve: give the axis some room around the value
        span = max(abs(lo), 1.0)
        lo, hi = lo - span / 2, hi + span / 2
        span = hi - lo
    step = nice_step(span)
    start = math.floor(round(lo / step, 9)) * step
    stop = math.ceil(round(hi / step, 9)) * step
    return round(start, 10), round(stop, 10), round(step, 10)


def _sample_and_segment(
    fx, fy, t0: float, t1: float, samples: int = SAMPLES
) -> tuple[list[list[tuple[float, float]]], float]:
    """Sample x(t), y(t) and split into segments at discontinuities.

    Pure helper: no Manim, no scene, no warnings.  Returns
    ``(segments, data_range)`` where each segment is a list of (x, y) points.

    Splitting occurs when:
    1. Consecutive valid points jump by more than the scale-aware threshold
       (typical per-sample step * 10).
    2. Sample indices are non-consecutive (a sample failed or produced a
       non-finite value between them).

    This heuristic cannot perfectly detect every discontinuity or every
    non-finite gap.
    """
    all_pts: list[tuple[float, float]] = []
    valid_indices: list[int] = []

    for i in range(samples):
        t = t0 + (t1 - t0) * i / (samples - 1)
        try:
            x = fx(t)
            y = fy(t)
        except Exception:
            continue
        if math.isfinite(x) and math.isfinite(y):
            all_pts.append((x, y))
            valid_indices.append(i)

    if not all_pts:
        return [], 0.0

    xs = [pt[0] for pt in all_pts]
    ys = [pt[1] for pt in all_pts]
    data_range = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    expected_step = data_range / (samples - 1)
    jump_threshold = expected_step * 10.0

    segments: list[list[tuple[float, float]]] = []
    current_segment: list[tuple[float, float]] = []
    prev_point: tuple[float, float] | None = None
    prev_idx = valid_indices[0]

    for idx, pt in zip(valid_indices, all_pts):
        if prev_point is not None:
            if idx != prev_idx + 1:
                if current_segment:
                    segments.append(current_segment)
                current_segment = [pt]
                prev_point = pt
                prev_idx = idx
                continue
            dx = abs(pt[0] - prev_point[0])
            dy = abs(pt[1] - prev_point[1])
            if dx > jump_threshold or dy > jump_threshold:
                if current_segment:
                    segments.append(current_segment)
                current_segment = [pt]
            else:
                current_segment.append(pt)
        else:
            current_segment.append(pt)

        prev_point = pt
        prev_idx = idx

    if current_segment:
        segments.append(current_segment)

    return [s for s in segments if len(s) >= 2], data_range


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

        # Sample x(t), y(t) and split at discontinuities via the pure helper.
        segments, data_range = _sample_and_segment(fx, fy, t0, t1, SAMPLES)

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
        pad = 0.05 * data_range
        x_start, x_stop, x_step = _nice_axis(x_lo - pad, x_hi + pad)
        y_start, y_stop, y_step = _nice_axis(y_lo - pad, y_hi + pad)

        try:
            axes = Axes(
                x_range=[x_start, x_stop, x_step],
                y_range=[y_start, y_stop, y_step],
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
        fit_in_room(scene, whole)

        clock = Clock(scene, 4.0)
        clock.play(FadeIn(title), run_time=0.8)
        clock.play(FadeIn(axes), run_time=0.8)  # axes appear first
        for curve in curves:
            clock.play(Create(curve), run_time=1.2 / len(curves))  # curves drawn after axes
        if label:
            clock.play(FadeIn(label_mob), run_time=0.4)
        clock.finish()

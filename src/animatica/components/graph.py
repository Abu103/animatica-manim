"""Graph: axes plus one or two plotted curves. Always 4.0 s.
Singularities become gaps, never NaN lines.

When ``approx_fn`` is given, both the original function and the
approximation are drawn on the same axes with distinct colors and a
color-matched legend, so the viewer can visually compare them.
"""
from __future__ import annotations

import math
import re
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, text_card, warn
from animatica.components._latex import explain_latex_failure, latex_to_plain
from animatica.components.base import Component
from animatica.native import sample_function
from animatica.storyboard.models import MAX_TEXT
from animatica.storyboard.safety import parse_function

SAMPLES = 400
DURATION = 4.0

_MATH_HINT = re.compile(r"(?<=[A-Za-z0-9])[\\^_\/]|[\\^_\/](?=[A-Za-z0-9])")


def looks_like_math(label: str) -> bool:
    """True when the label carries math notation (^, _, backslash, or /
    adjacent to an alphanumeric character)."""
    return _MATH_HINT.search(label) is not None


def make_label(scene, text: str, colors):
    """MathTex label for math text, plain Text otherwise; on any LaTeX failure,
    warn and degrade to Text(latex_to_plain(text)) so the beat never aborts."""
    from manim import MathTex, Text

    if looks_like_math(text):
        try:
            return MathTex(text, font_size=MIN_FONT_SIZE, color=colors.text)
        except Exception as exc:  # LaTeX missing/broken: readable fallback, never abort
            warn(scene, f"graph label: LaTeX failed for {text!r} ({explain_latex_failure(exc)})")
            return Text(latex_to_plain(text), font_size=MIN_FONT_SIZE, color=colors.text)
    return Text(text, font_size=MIN_FONT_SIZE, color=colors.text)


def clip_segments(segs: list[list[tuple[float, float]]], y_range: tuple[float, float]):
    """Split segments wherever a point leaves [y_min, y_max]; keep only runs of 2+ points."""
    lo, hi = y_range
    out, cur = [], []
    for seg in segs:
        for x, y in seg:
            if lo <= y <= hi:
                cur.append((x, y))
            else:
                if len(cur) >= 2:
                    out.append(cur)
                cur = []
        if len(cur) >= 2:
            out.append(cur)
        cur = []
    return out


def nice_step(span: float, target: int = 6) -> float:
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


class Graph(Component):
    name: ClassVar[str] = "graph"
    # LaTeX is not a hard requirement: axis-number rendering degrades gracefully
    # when LaTeX is unavailable. required_capabilities stays empty.

    class Params(BaseModel):
        fn: str = Field(min_length=1, max_length=MAX_TEXT)
        approx_fn: str = Field(default="", max_length=MAX_TEXT)
        x_range: tuple[float, float]
        y_range: tuple[float, float]
        label: str = Field(default="", max_length=MAX_TEXT)
        approx_label: str = Field(default="", max_length=MAX_TEXT)

        @field_validator("fn")
        @classmethod
        def _safe_fn(cls, v: str) -> str:
            parse_function(v)  # raises UnsafeInput (a ValueError) on anything outside the allowlist
            return v

        @field_validator("approx_fn")
        @classmethod
        def _safe_approx_fn(cls, v: str) -> str:
            if v.strip():
                parse_function(v)  # same safe parser, only when non-empty
            return v

        @model_validator(mode="after")
        def _ranges(self):
            for name in ("x_range", "y_range"):
                lo, hi = getattr(self, name)
                if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
                    raise ValueError(f"{name} must be two finite numbers with min < max")
            return self

    def duration(self, p: BaseModel) -> float:
        return DURATION

    def fallback_text(self, p: BaseModel) -> str:
        parts = [f"y = {p.fn}"]
        if p.approx_fn.strip():
            parts.append(f"approx y = {p.approx_fn}")
        return " | ".join(parts)  # type: ignore[attr-defined]

    def _range_clipped(self, fn_expr: str, x0: float, x1: float, y0: float, y1: float) -> bool:
        """Return True if the function's boundary values fall outside [y0, y1],
        meaning part of the curve is clipped by the requested range.

        Only finite values outside the range count as clipping; NaN/inf at
        domain boundaries are undefined, not clipped.
        """
        try:
            fn = parse_function(fn_expr)
            for x in (x0, x1):
                v = fn(x)
                if math.isfinite(v) and (v < y0 or v > y1):
                    return True
        except Exception:
            # If we can't evaluate, assume no clipping (fail-safe).
            return False
        return False

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, LEFT, RIGHT, UP, Axes, Create, FadeIn, Line, Text, VGroup, VMobject
        from manim import config
        prepare(scene, colors)
        (x0, x1), (y0, y1) = p.x_range, p.y_range
        try:
            segs = clip_segments(sample_function(parse_function(p.fn), (x0, x1), SAMPLES, y_range=(y0, y1)), (y0, y1))
            if not segs:
                raise ValueError("no visible points inside the y range")
            approx_segs = []
            if p.approx_fn.strip():
                approx_segs = clip_segments(
                    sample_function(parse_function(p.approx_fn), (x0, x1), SAMPLES, y_range=(y0, y1)), (y0, y1)
                )
            def make_axes(numbers: bool):
                return Axes(
                    x_range=[x0, x1, nice_step(x1 - x0)], y_range=[y0, y1, nice_step(y1 - y0)],
                    x_length=10.0, y_length=5.0,
                    axis_config={"color": colors.muted, "include_numbers": numbers, "font_size": MIN_FONT_SIZE - 6},
                )
            try:
                axes = make_axes(True)
            except Exception as tex_exc:  # tick numbers need LaTeX: keep the graph, drop the numbers
                warn(scene, f"graph: axis numbers skipped (LaTeX unavailable). {explain_latex_failure(tex_exc)}")
                axes = make_axes(False)
        except Exception as exc:  # degrade, never abort the video
            warn(scene, f"graph: could not draw {p.fn!r} ({type(exc).__name__}: {exc}); showing plain text")
            text_card(scene, self.fallback_text(p), colors, DURATION)
            return

        curves = []
        for seg in segs:
            curve = VMobject(stroke_color=colors.accent, stroke_width=6, fill_opacity=0)
            curve.set_points_as_corners([axes.c2p(x, y) for x, y in seg])
            curves.append(curve)
        approx_curves = []
        for seg in approx_segs:
            curve = VMobject(stroke_color=colors.text_contrast if hasattr(colors, "text_contrast") else colors.text, stroke_width=4, fill_opacity=0)
            curve.set_points_as_corners([axes.c2p(x, y) for x, y in seg])
            approx_curves.append(curve)

        plot = VGroup(axes, *curves, *approx_curves)
        title = make_label(scene, p.label, colors) if p.label else None
        whole = VGroup(title, plot).arrange(DOWN, buff=0.3) if title else plot
        # Leave extra headroom above the bottom caption band so x-axis tick
        # labels never collide with multi-line captions. Account for actual
        # rendered bounds by capping height below the nominal frame height.
        fit(whole, scale_up=False, max_height=config.frame_height - 3.0)
        # Build a color-matched legend when both curves are present.
        legend = None
        if p.approx_fn.strip() and (p.label or p.approx_label):
            items = []
            if p.label:
                swatch = Line(LEFT * 0.35, RIGHT * 0.35, stroke_color=colors.accent, stroke_width=5)
                txt = Text(p.label, font_size=MIN_FONT_SIZE - 4, color=colors.text)
                items.append(VGroup(swatch, txt).arrange(RIGHT, buff=0.2))
            if p.approx_label:
                approx_color = colors.text_contrast if hasattr(colors, "text_contrast") else colors.text
                swatch = Line(LEFT * 0.35, RIGHT * 0.35, stroke_color=approx_color, stroke_width=4)
                txt = Text(p.approx_label, font_size=MIN_FONT_SIZE - 4, color=colors.text)
                items.append(VGroup(swatch, txt).arrange(RIGHT, buff=0.2))
            legend = VGroup(*items).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
            # Anchor legend in the top-right corner of the plot area.
            legend.move_to(axes.get_corner(UP + RIGHT) + DOWN * 0.4 + LEFT * 0.4)
        clock = Clock(scene, DURATION)
        clock.play(FadeIn(axes), *([FadeIn(title)] if title else []), run_time=1.0)
        if legend is not None:
            clock.play(FadeIn(legend), run_time=0.6)
        per = max(0.05, 2.0 / (len(curves) + len(approx_curves)))
        for curve in curves:
            clock.play(Create(curve), run_time=per)
        for curve in approx_curves:
            clock.play(Create(curve), run_time=per)
        # Warn when a curve is clipped by the requested y-range so the viewer
        # is not misled into thinking the function vanished.
        clipped = []
        if self._range_clipped(p.fn, x0, x1, y0, y1):
            clipped.append(p.label or p.fn)
        if p.approx_fn.strip() and self._range_clipped(p.approx_fn, x0, x1, y0, y1):
            clipped.append(p.approx_label or p.approx_fn)
        if clipped:
            warn(scene, f"graph: curve(s) {', '.join(clipped)} clipped by y-range [{y0}, {y1}]; part lies outside the visible area")
        clock.finish()

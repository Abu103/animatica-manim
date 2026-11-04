"""Graph: axes plus a plotted curve drawn on. Always 4.0 s. Singularities become gaps, never NaN lines."""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, text_card, warn
from animatica.components._latex import explain_latex_failure
from animatica.components.base import Component
from animatica.native import sample_function
from animatica.storyboard.models import MAX_TEXT
from animatica.storyboard.safety import parse_function

SAMPLES = 400
DURATION = 4.0


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

    class Params(BaseModel):
        fn: str = Field(min_length=1, max_length=MAX_TEXT)
        x_range: tuple[float, float]
        y_range: tuple[float, float]
        label: str = Field(default="", max_length=MAX_TEXT)

        @field_validator("fn")
        @classmethod
        def _safe_fn(cls, v: str) -> str:
            parse_function(v)  # raises UnsafeInput (a ValueError) on anything outside the allowlist
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
        return f"{p.label}\ny = {p.fn}".strip()  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, Axes, Create, FadeIn, Text, VGroup, VMobject
        prepare(scene, colors)
        (x0, x1), (y0, y1) = p.x_range, p.y_range
        try:
            segs = clip_segments(sample_function(parse_function(p.fn), (x0, x1), SAMPLES, y_range=(y0, y1)), (y0, y1))
            if not segs:
                raise ValueError("no visible points inside the y range")
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
        plot = VGroup(axes, *curves)
        title = Text(p.label, font_size=MIN_FONT_SIZE, color=colors.text) if p.label else None
        whole = VGroup(title, plot).arrange(DOWN, buff=0.3) if title else plot
        fit(whole)  # scales axes and curves together (curves are children of `plot`)
        clock = Clock(scene, DURATION)
        clock.play(FadeIn(axes), *([FadeIn(title)] if title else []), run_time=1.0)
        per = max(0.05, 2.0 / len(curves))
        for curve in curves:
            clock.play(Create(curve), run_time=per)
        clock.finish()


"""Graph: axes plus one or two plotted curves. Always 4.0 s.
Singularities become gaps, never NaN lines.

When ``approx_fn`` is given, both the original function and the
approximation are drawn on the same axes with distinct colors and a legend
that names both curves. The legend is what tells the viewer which curve is
which, so it is built whenever there are two curves -- whether or not the
model labelled them -- and it is placed above the plot, where no curve can
run through it.

The graph lays itself out against the caption the renderer burns in: the
plot is sized so the axis numbers stay clear of the caption.
"""
from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from animatica.components._draw import (
    FADE_OUT,
    MIN_FONT_SIZE,
    SAFE_AREA_MARGIN,
    Clock,
    latex_expression,
    looks_like_math,
    prepare,
    text_card,
    warn,
    wrap,
)
from animatica.components._latex import explain_latex_failure, latex_to_plain
from animatica.components.base import Component
from animatica.native import sample_function
from animatica.storyboard.models import MAX_TEXT
from animatica.storyboard.safety import parse_function

SAMPLES = 400
DURATION = 4.0

#: Clearance kept between the caption's top and the bottom of the plot, so
#: the x-axis numbers never end up under the caption.
TICK_CLEARANCE = 0.16

#: Vertical gap between the blocks above the plot (title, legend).
BLOCK_BUFF = 0.3

#: Characters per line of a legend entry written as prose. A long label
#: wraps instead of growing past the safe area.
LEGEND_WRAP = 26

#: Slack left between the band and the content, so rounding never pushes
#: the plot past the safe area.
LAYOUT_SLACK = 0.08

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

    #: The legend of the last beat, for tests that check it was drawn.
    last_legend = None

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

    # -- layout ------------------------------------------------------------

    def _band(self, scene) -> tuple[float, float, float]:
        """The vertical band the graph may use, and the width it may use.

        The band runs from just above the caption the renderer burns in to
        the top of the safe area. It cannot be a constant: the caption's
        height depends on how its text wraps, so a one-line caption leaves
        more room than a three-line one.
        """
        from manim import config

        margin_y = config.frame_height * SAFE_AREA_MARGIN
        margin_x = config.frame_width * SAFE_AREA_MARGIN
        caption = getattr(scene, "caption_mobject", None)
        if caption is not None:
            floor = caption.get_top()[1] + TICK_CLEARANCE
        else:
            floor = -config.frame_height / 2 + margin_y + 0.05
        top = config.frame_height / 2 - margin_y
        width = config.frame_width - 2 * margin_x
        return floor, top, width

    def _legend_entry(self, scene, name: str, color, stroke_width: int, colors, expression: bool):
        """One legend row: a colour swatch and the name of the curve.

        A curve named by its own expression is typeset as LaTeX, so the
        viewer reads ``e^{x}`` and not the source code ``exp(x)``. A label
        written as prose stays prose, and wraps instead of growing past the
        safe area.
        """
        from manim import LEFT, RIGHT, Line, MathTex, Text, VGroup

        swatch = Line(LEFT * 0.35, RIGHT * 0.35, stroke_color=color, stroke_width=stroke_width)
        if expression or looks_like_math(name):
            source = latex_expression(name)
            try:
                label = MathTex(source, font_size=MIN_FONT_SIZE, color=colors.text)
            except Exception as exc:  # LaTeX missing/broken: readable fallback, never abort
                warn(scene, f"graph legend: LaTeX failed for {name!r} ({explain_latex_failure(exc)})")
                label = Text(latex_to_plain(source), font_size=MIN_FONT_SIZE, color=colors.text)
        else:
            label = Text(wrap(name, LEGEND_WRAP), font_size=MIN_FONT_SIZE, color=colors.text)
        return VGroup(swatch, label).arrange(RIGHT, buff=0.2)

    def _text_blocks(self, scene, p, colors):
        """The text that sits above the plot: the legend, or the title.

        A graph with two curves needs a legend -- without it the viewer
        cannot tell the approximation from the function -- so it is built
        whenever there is a second curve, and it names the curves from the
        labels when there are any and from the expressions when there are
        not. A graph with one curve keeps its label as a title.
        """
        from manim import DOWN, LEFT, VGroup

        legend = None
        if p.approx_fn.strip():
            approx_color = colors.text_contrast if hasattr(colors, "text_contrast") else colors.text
            rows = [
                self._legend_entry(
                    scene, p.label or p.fn, colors.accent, 5, colors, expression=not p.label
                ),
                self._legend_entry(
                    scene, p.approx_label or p.approx_fn, approx_color, 4, colors,
                    expression=not p.approx_label,
                ),
            ]
            legend = VGroup(*rows).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        self.last_legend = legend

        title = None
        if legend is None and p.label:
            title = make_label(scene, p.label, colors)
        return title, legend

    def _make_axes(self, scene, p, colors, plot_h: float, safe_w: float):
        """The axes, sized to the space the plot may use.

        The axis numbers hang below and beside the axes, so the axes are
        measured after they are built and shortened until the whole plot
        fits the band. The numbers keep their font size: only the plot is
        resized, never the text.
        """
        from manim import Axes

        x0, x1 = p.x_range
        y0, y1 = p.y_range
        numbers = True

        def build(x_len: float, y_len: float):
            return Axes(
                x_range=[x0, x1, nice_step(x1 - x0)],
                y_range=[y0, y1, nice_step(y1 - y0)],
                x_length=x_len,
                y_length=y_len,
                axis_config={
                    "color": colors.muted,
                    "include_numbers": numbers,
                    "font_size": MIN_FONT_SIZE - 6,
                },
            )

        axes = None
        y_len = max(1.0, plot_h - 0.45)
        x_len = max(2.0, 2.0 * y_len)
        for _ in range(8):
            try:
                axes = build(x_len, y_len)
            except Exception as tex_exc:  # tick numbers need LaTeX: keep the graph, drop the numbers
                if numbers:
                    warn(
                        scene,
                        f"graph: axis numbers skipped (LaTeX unavailable). {explain_latex_failure(tex_exc)}",
                    )
                    numbers = False
                    continue
                raise
            too_tall = axes.height - plot_h
            too_wide = axes.width - safe_w
            if too_tall <= 0.02 and too_wide <= 0.02:
                break
            if too_tall > 0:
                y_len = max(1.0, y_len - too_tall)
                x_len = min(x_len, 2.0 * y_len)
            if too_wide > 0:
                x_len = max(2.0, x_len - too_wide)
        return axes

    # -- playback ----------------------------------------------------------

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, UP, Create, FadeIn, VGroup, VMobject
        prepare(scene, colors)
        (x0, x1), (y0, y1) = p.x_range, p.y_range
        try:
            segs = clip_segments(
                sample_function(parse_function(p.fn), (x0, x1), SAMPLES, y_range=(y0, y1)), (y0, y1)
            )
            if not segs:
                raise ValueError("no visible points inside the y range")
            approx_segs = []
            if p.approx_fn.strip():
                approx_segs = clip_segments(
                    sample_function(parse_function(p.approx_fn), (x0, x1), SAMPLES, y_range=(y0, y1)), (y0, y1)
                )
        except Exception as exc:  # degrade, never abort the video
            warn(scene, f"graph: could not draw {p.fn!r} ({type(exc).__name__}: {exc}); showing plain text")
            text_card(scene, self.fallback_text(p), colors, DURATION)
            return

        floor, top, safe_w = self._band(scene)
        title, legend = self._text_blocks(scene, p, colors)
        blocks = [b for b in (title, legend) if b is not None]
        reserved = sum(b.height for b in blocks) + BLOCK_BUFF * len(blocks)
        plot_h = max(1.5, (top - floor) - reserved - LAYOUT_SLACK)

        axes = self._make_axes(scene, p, colors, plot_h, safe_w)

        curves = []
        for seg in segs:
            curve = VMobject(stroke_color=colors.accent, stroke_width=6, fill_opacity=0)
            curve.set_points_as_corners([axes.c2p(x, y) for x, y in seg])
            curves.append(curve)
        approx_curves = []
        for seg in approx_segs:
            curve = VMobject(
                stroke_color=colors.text_contrast if hasattr(colors, "text_contrast") else colors.text,
                stroke_width=4,
                fill_opacity=0,
            )
            curve.set_points_as_corners([axes.c2p(x, y) for x, y in seg])
            approx_curves.append(curve)

        plot = VGroup(axes, *curves, *approx_curves)
        if plot.height > plot_h:  # last resort: shrink the plot, never the text
            plot.scale_to_fit_height(plot_h)
        whole = VGroup(*blocks, plot)
        whole.arrange(DOWN, buff=BLOCK_BUFF)  # the legend sits above the plot
        whole.move_to([0, (floor + top) / 2, 0])
        if whole.get_bottom()[1] < floor:
            whole.shift(UP * (floor - whole.get_bottom()[1]))

        # -- timing: the beat fills its budget in whole video frames -------
        clock = Clock(scene, DURATION)
        total_frames = clock.frames(DURATION)
        fade_frames = clock.frames(FADE_OUT)
        content_frames = max(1, total_frames - fade_frames)
        axes_frames = clock.frames(1.0)
        legend_frames = clock.frames(0.6) if legend is not None else 0
        curve_frames = content_frames - axes_frames - legend_frames
        if curve_frames < 1:
            legend_frames = 0
            curve_frames = content_frames - axes_frames
        if curve_frames < 1:
            axes_frames = max(1, content_frames - 1)
            curve_frames = content_frames - axes_frames

        all_curves = curves + approx_curves
        if len(all_curves) <= curve_frames:
            # One animation per curve: every curve is drawn on its own.
            chunks = [[curve] for curve in all_curves]
        else:
            # More curves than frames: draw them in groups, so the beat still
            # fits the duration it declared.
            size = math.ceil(len(all_curves) / curve_frames)
            chunks = [all_curves[i:i + size] for i in range(0, len(all_curves), size)]
        per_chunk = curve_frames // len(chunks) if chunks else 0
        extra = curve_frames - per_chunk * len(chunks)

        clock.play(FadeIn(axes), *([FadeIn(title)] if title else []), run_time=clock.seconds(axes_frames))
        if legend is not None:
            clock.play(FadeIn(legend), run_time=clock.seconds(legend_frames))
        for i, chunk in enumerate(chunks):
            frames = per_chunk + (1 if i < extra else 0)
            target = chunk[0] if len(chunk) == 1 else VGroup(*chunk)
            clock.play(Create(target), run_time=clock.seconds(frames))

        # Warn when a curve is clipped by the requested y-range so the viewer
        # is not misled into thinking the function vanished.
        clipped = []
        if self._range_clipped(p.fn, x0, x1, y0, y1):
            clipped.append(p.label or p.fn)
        if p.approx_fn.strip() and self._range_clipped(p.approx_fn, x0, x1, y0, y1):
            clipped.append(p.approx_label or p.approx_fn)
        if clipped:
            warn(scene, f"graph: curve(s) {', '.join(clipped)} clipped by y-range [{y0}, {y1}]; part lies outside the visible area")
        clock.finish(fade_out=clock.seconds(fade_frames))

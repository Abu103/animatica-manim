"""Signal spectrum engine: sum of sinusoids sampled over time, then its FFT.

Pure data and facts live here (no Manim at import time): the drawing reads the
same ``_data`` the facts do, so a fact cannot drift from the picture (5.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import (
    MIN_FONT_SIZE,
    Clock,
    fit,
    fit_in_room,
    prepare,
    text_card,
    warn,
)
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT
from animatica.verify.facts import Fact

N = 256


@dataclass(frozen=True)
class SpectrumData:
    t: np.ndarray
    x: np.ndarray
    freqs: np.ndarray
    mags: np.ndarray
    peaks: list[int]  # bin indices; integer cycles per window, so exact


class Wave(BaseModel):
    freq: int = Field(ge=1, le=40)
    amp: float = Field(ge=0.1, le=5.0)
    phase: float = Field(default=0.0, ge=-3.2, le=3.2)


def _data(p: BaseModel) -> SpectrumData:
    """Sample the waves and take the magnitude spectrum. No drawing, no Manim."""
    t = np.arange(N) / N
    x = sum(w.amp * np.sin(2 * np.pi * w.freq * t + w.phase) for w in p.waves)  # type: ignore[attr-defined]
    mags = 2 * abs(np.fft.rfft(x)) / N
    mags[0] /= 2
    peaks = [k for k in range(1, len(mags)) if mags[k] > 0.05 * mags.max()]
    return SpectrumData(t=t, x=x, freqs=np.arange(len(mags)), mags=mags, peaks=peaks)


def _time_panel(data: SpectrumData, colors, height: float = 2.1, width: float = 10.0):
    """The time-domain curve and its axis, from the same samples as the facts."""
    from manim import DOWN, RIGHT, Line, Text, VMobject, VGroup

    lo, hi = float(data.x.min()), float(data.x.max())
    span = max(hi - lo, 1e-9)
    mid = (lo + hi) / 2
    points = [(-width / 2 + width * float(t), height * (float(v) - mid) / span, 0)
              for t, v in zip(data.t, data.x)]
    curve = VMobject(stroke_color=colors.accent, stroke_width=6, fill_opacity=0)
    curve.set_points_as_corners(points)
    axis = Line([-width / 2, 0, 0], [width / 2, 0, 0], color=colors.muted, stroke_width=2)
    label = (Text("Time", font_size=MIN_FONT_SIZE, color=colors.muted)
             .next_to(axis, DOWN, buff=0.12).align_to(axis, RIGHT))
    # The samples are drawn between -height/2 and +height/2, including at the
    # right end of the axis. Parking the label a full half-height below the
    # axis puts it past the curve's lowest point, so the two cannot touch.
    label.shift(DOWN * (height / 2))
    return VGroup(axis, curve, label), curve, [axis, label]


def _spectrum_panel(data: SpectrumData, colors, height: float = 2.0, width: float = 10.0):
    """One bar per peak, at its integer frequency; numbers come from _data."""
    from manim import DOWN, Line, Rectangle, Text, VGroup

    baseline = Line([-width / 2, 0, 0], [width / 2, 0, 0],
                    color=colors.muted, stroke_width=2)
    peaks = data.peaks
    max_mag = max(float(data.mags.max()), 1e-9)
    fmax = max(peaks) if peaks else 1
    xs = [-width / 2 + width * k / (fmax + 1) for k in peaks]
    if any(b - a < 1.2 for a, b in zip(xs, xs[1:])):
        slot = width / (len(peaks) + 1)
        xs = [-width / 2 + slot * (i + 1) for i in range(len(peaks))]
    bars, numbers = [], []
    for k, cx in zip(peaks, xs):
        bar_h = 0.15 + height * float(data.mags[k]) / max_mag
        bar = Rectangle(width=0.9, height=bar_h, stroke_width=0, fill_opacity=1.0,
                        fill_color=colors.accent2)
        bar.move_to([cx, bar_h / 2, 0])
        number = Text(str(int(k)), font_size=MIN_FONT_SIZE, color=colors.text)
        number.next_to(bar, DOWN, buff=0.12)
        bars.append(bar)
        numbers.append(number)
    label = Text("Frequency (cycles per window)", font_size=MIN_FONT_SIZE, color=colors.muted)
    label.next_to(VGroup(*numbers) if numbers else baseline, DOWN, buff=0.22)
    return VGroup(baseline, *bars, *numbers, label), bars, [baseline, label, *numbers]


class SignalSpectrum(Component):
    name: ClassVar[str] = "signal_spectrum"
    domain: ClassVar[str] = "frequency"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        waves: list[Wave] = Field(min_length=1, max_length=4)
        show: Literal["time", "spectrum", "both"] = "both"

        @model_validator(mode="after")
        def _distinct_freqs(self):
            freqs = [w.freq for w in self.waves]
            if len(freqs) != len(set(freqs)):
                raise ValueError("wave frequencies must be distinct")
            return self

    def duration(self, p: BaseModel) -> float:
        return 5.0 if p.show == "both" else 3.5  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [p.title]  # type: ignore[attr-defined]
        for k in _data(p).peaks:
            lines.append(f"peak at {k} cycles per window")
        return "\n".join(lines)

    def facts(self, p: BaseModel) -> list[Fact]:
        data = _data(p)
        lo, hi = round(float(data.x.min()), 3), round(float(data.x.max()), 3)
        return [Fact("peak", "signal", (k, round(float(data.mags[k]), 3)),
                     f"spectrum has a peak at {k} cycles per window "
                     f"with amplitude {round(float(data.mags[k]), 3)}")
                for k in data.peaks] + [
            Fact("range", "signal", (lo, hi),
                 f"signal ranges from {lo} to {hi}"),
            Fact("domain", "signal", "frequency",
                 "signal_spectrum draws the signal over time and its frequency spectrum"),
        ]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, Create, FadeIn, GrowFromEdge, LaggedStart, Text, VGroup, config
        prepare(scene, colors)
        try:
            data = _data(p)
            total = self.duration(p)
            curve = bars = None
            time_static = spectrum_static = []
            if p.show in ("time", "both"):
                time_panel, curve, time_static = _time_panel(data, colors)
            if p.show in ("spectrum", "both"):
                spectrum_panel, bars, spectrum_static = _spectrum_panel(data, colors)
            if p.show == "both":
                panels = VGroup(time_panel, spectrum_panel).arrange(DOWN, buff=0.45)
            else:
                panels = time_panel if p.show == "time" else spectrum_panel
            title = Text(p.title, font_size=MIN_FONT_SIZE + 6, color=colors.text)
            fit(title, max_width=config.frame_width - 2.0, scale_up=False)
            whole = VGroup(title, panels).arrange(DOWN, buff=0.3)
            fit_in_room(scene, whole, scale_up=False)
            static = [title, *time_static, *spectrum_static]
        except Exception as exc:  # degrade, never abort the video (same policy as graph)
            warn(scene, f"signal_spectrum: could not draw ({type(exc).__name__}: {exc}); showing plain text")
            text_card(scene, self.fallback_text(p), colors, self.duration(p))
            return

        clock = Clock(scene, total)
        clock.play(FadeIn(*static), run_time=0.6)
        if curve is not None:
            clock.play(Create(curve), run_time=2.0 if p.show == "both" else 1.8)
        if bars:
            clock.play(LaggedStart(*[GrowFromEdge(bar, DOWN) for bar in bars], lag_ratio=0.15),
                       run_time=1.2)
        clock.finish()

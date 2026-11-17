"""Signal spectrum engine: sum of sinusoids sampled over time, then its FFT.

Pure data and facts live here (no Manim): the drawing in ``play()`` reads the
same ``_data`` the facts do, so a fact cannot drift from the picture (5.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator

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
        raise NotImplementedError  # V3b adds the drawing

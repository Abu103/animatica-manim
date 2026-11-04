"""Bar/pad height scaling that never imports Manim.

Linear heights make small values invisible when one value dwarfs the rest (Fibonacci 0..15:
610 vs 1). ``auto`` picks sqrt or log from the spread, so weak models never have to decide.
Labels always show the true value; the chart shows a small note when it is not linear.
"""
from __future__ import annotations

import math
import statistics
from typing import Literal

Scale = Literal["auto", "linear", "sqrt", "log"]
NOTES = {"sqrt": "height ~ square root of value", "log": "height ~ log of value"}


def resolve_scale(values: list[float], scale: str = "auto") -> str:
    if scale != "auto":
        return scale
    pos = [v for v in values if v > 0]
    if len(pos) < 3:
        return "linear"
    ratio = max(pos) / statistics.median(pos)
    return "log" if ratio > 60 else "sqrt" if ratio > 8 else "linear"


def scaled_heights(values: list[float], max_h: float, min_h: float, scale: str = "auto") -> tuple[list[float], str]:
    """Heights in scene units (each >= min_h) and the scale that was actually used."""
    used = resolve_scale(values, scale)
    top = max(values) or 1.0
    if used == "sqrt":
        f = lambda v: math.sqrt(v / top)
    elif used == "log":
        f = lambda v: math.log1p(v) / math.log1p(top)
    else:
        f = lambda v: v / top
    return [max(min_h, max_h * f(v)) for v in values], used


"""Tests for _draw.fit() — scaling behavior for landscape and portrait.

fit() scales down content that exceeds frame bounds, then scales up
proportionally to fill available space (limited by min(scale_w, scale_h)
so content never overflows).
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from animatica.components._draw import fit


class _FakeMobject:
    """Minimal stand-in for a Manim mobject with width/height and scale()."""

    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height
        self.scale_calls: list[float] = []

    def scale(self, factor: float) -> None:
        self.scale_calls.append(factor)
        self.width *= factor
        self.height *= factor

    def scale_to_fit_width(self, width: float) -> None:
        factor = width / self.width if self.width > 0 else 1.0
        self.width = width
        self.height *= factor

    def scale_to_fit_height(self, height: float) -> None:
        factor = height / self.height if self.height > 0 else 1.0
        self.height = height
        self.width *= factor


@contextmanager
def _frame_dims(frame_width: float, frame_height: float):
    """Temporarily set manim config frame dimensions, restoring on exit."""
    from manim import config

    old_w = config.frame_width
    old_h = config.frame_height
    config.frame_width = frame_width
    config.frame_height = frame_height
    try:
        yield
    finally:
        config.frame_width = old_w
        config.frame_height = old_h


# ---------------------------------------------------------------------------
# scale-down behavior (content too large for frame)
# ---------------------------------------------------------------------------

def test_fit_scales_down_wide_content():
    """Content wider than frame scales down to fit width, not height."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=20.0, height=5.0)
        result = fit(m)
        assert result is m
        # width clamped to frame_width - 1.0 = 13.22, height scales proportionally
        assert abs(m.width - 13.22) < 1e-6
        assert abs(m.height - 5.0 * (13.22 / 20.0)) < 1e-6
        assert len(m.scale_calls) == 0  # scale_to_fit_width used, not scale()


def test_fit_scales_down_tall_content():
    """Content taller than frame scales down to fit height."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=5.0, height=10.0)
        fit(m)
        # height clamped to frame_height - 2.4 = 5.6, width scales proportionally
        assert abs(m.height - 5.6) < 1e-6
        assert abs(m.width - 5.0 * (5.6 / 10.0)) < 1e-6


def test_fit_scales_down_both_dimensions():
    """Content exceeding both dimensions: width clamped first, then height."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=30.0, height=15.0)
        fit(m)
        # After width clamp: width=13.22, height=15*(13.22/30)=6.61
        # Then height clamp: height=5.6, width=13.22*(5.6/6.61)=11.20
        assert abs(m.height - 5.6) < 1e-6
        assert abs(m.width - 11.20) < 1e-2


# ---------------------------------------------------------------------------
# scale-up behavior (content smaller than frame)
# ---------------------------------------------------------------------------

def test_fit_scales_up_small_content():
    """Small content scales up proportionally, limited by min(scale_w, scale_h)."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=3.0, height=2.0)
        fit(m)
        # scale_w = 13.22/3.0 = 4.41, scale_h = 5.6/2.0 = 2.8, scale = 2.8
        assert abs(m.scale_calls[-1] - 2.8) < 1e-6
        assert abs(m.width - 3.0 * 2.8) < 1e-6
        assert abs(m.height - 2.0 * 2.8) < 1e-6


def test_fit_does_not_overflow_after_scale_up():
    """After scale-up, neither dimension exceeds its max bound."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=3.0, height=2.0)
        fit(m)
        assert m.width <= 13.22 + 1e-6
        assert m.height <= 5.6 + 1e-6


def test_fit_content_already_fills_width_no_upscale():
    """Content that fills width but not height does not scale up (scale_w=1.0)."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=13.22, height=3.0)
        fit(m)
        assert len(m.scale_calls) == 0
        assert m.width == 13.22
        assert m.height == 3.0


def test_fit_content_already_fills_height_no_upscale():
    """Content that fills height but not width does not scale up (scale_h=1.0)."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=3.0, height=5.6)
        fit(m)
        assert len(m.scale_calls) == 0
        assert m.width == 3.0
        assert m.height == 5.6


# ---------------------------------------------------------------------------
# nested groups
# ---------------------------------------------------------------------------

def test_fit_nested_group_scales_as_whole():
    """fit() on a VGroup scales the entire group; children keep relative sizes."""
    with _frame_dims(14.22, 8.0):
        # Simulate a group: outer mobject contains children with their own sizes
        outer = _FakeMobject(width=4.0, height=3.0)
        child = _FakeMobject(width=2.0, height=1.5)
        # fit() only sees the outer object; children aren't individually scaled
        fit(outer)
        assert abs(outer.scale_calls[-1] - (5.6 / 3.0)) < 1e-6  # scale_h is limiting
        # child unchanged (fit() doesn't recurse into children)
        assert child.width == 2.0
        assert child.height == 1.5


# ---------------------------------------------------------------------------
# readable text / captions
# ---------------------------------------------------------------------------

def test_fit_caption_not_distorted():
    """A wide short caption scales up proportionally without distortion."""
    with _frame_dims(14.22, 8.0):
        # Caption: wide (10.0) and short (0.8)
        m = _FakeMobject(width=10.0, height=0.8)
        fit(m)
        # scale_w = 13.22/10.0 = 1.322, scale_h = 5.6/0.8 = 7.0, scale = 1.322
        assert abs(m.scale_calls[-1] - 1.322) < 1e-6
        assert abs(m.width - 13.22) < 1e-6
        assert abs(m.height - 0.8 * 1.322) < 1e-6


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------

def test_fit_zero_width_no_division_by_zero():
    """Zero-width object is handled gracefully (no division by zero)."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=0.0, height=5.0)
        fit(m)  # should not raise
        assert len(m.scale_calls) == 0  # scale_w defaults to 1.0


def test_fit_zero_height_no_division_by_zero():
    """Zero-height object is handled gracefully."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=5.0, height=0.0)
        fit(m)  # should not raise
        assert len(m.scale_calls) == 0


def test_fit_exact_bounds_no_change():
    """Content exactly at frame bounds is not scaled."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=13.22, height=5.6)
        fit(m)
        assert len(m.scale_calls) == 0
        assert m.width == 13.22
        assert m.height == 5.6


def test_fit_returns_same_object():
    """fit() returns the same mobject instance (mutation in place)."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=3.0, height=2.0)
        result = fit(m)
        assert result is m


# ---------------------------------------------------------------------------
# portrait mode behavior
# ---------------------------------------------------------------------------

def test_fit_portrait_scales_up_to_fill_height():
    """Content scales up proportionally within landscape frame bounds."""
    with _frame_dims(14.22, 8.0):
        m = _FakeMobject(width=5.0, height=3.0)
        fit(m)
        # scale_w = 13.22/5.0 = 2.644, scale_h = 5.6/3.0 = 1.867, scale = 1.867
        assert abs(m.scale_calls[-1] - 1.867) < 1e-2
        assert abs(m.width - 5.0 * 1.867) < 1e-2
        assert abs(m.height - 3.0 * 1.867) < 1e-2

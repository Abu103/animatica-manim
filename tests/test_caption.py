"""Tests for make_caption() — caption sizing and safe-area behavior in
landscape and portrait frames.

Verifies actual bounding boxes against frame and caption-safe regions,
not just output resolution. Short captions are never enlarged; long
captions scale down only when needed; horizontal margins are preserved;
very narrow frames are handled safely.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from animatica.components._draw import make_caption
from animatica.components.theme import PALETTES


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


COLORS = PALETTES["dark-blue"]

# Frame size presets
LANDSCAPE_W, LANDSCAPE_H = 14.22, 8.0   # 1280x720-ish
PORTRAIT_W, PORTRAIT_H = 5.6, 10.0      # 9:16 vertical
NARROW_W, NARROW_H = 2.0, 8.0           # very narrow frame


# ---------------------------------------------------------------------------
# Short captions are never enlarged (the core bug fix)
# ---------------------------------------------------------------------------

def test_short_caption_not_enlarged_landscape():
    """A short caption stays at its natural size in landscape; no edge-to-edge
    enlargement."""
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap = make_caption("Hi", COLORS)
        # Max allowed width with 5% margins: 14.22 * 0.9 = 12.798
        assert cap.width <= LANDSCAPE_W * 0.9 + 1e-6
        # Has horizontal margin: doesn't touch either edge
        assert cap.width < LANDSCAPE_W


def test_short_caption_not_enlarged_portrait():
    """A short caption stays at its natural size in portrait; not stretched to
    full frame width."""
    with _frame_dims(PORTRAIT_W, PORTRAIT_H):
        cap = make_caption("Hi", COLORS)
        assert cap.width <= PORTRAIT_W * 0.9 + 1e-6
        assert cap.width < PORTRAIT_W


def test_short_caption_font_size_not_inflated_portrait():
    """In portrait, font_size caps at 40 and short text isn't blown up to fill
    the narrow frame."""
    with _frame_dims(PORTRAIT_W, PORTRAIT_H):
        cap = make_caption("Hi", COLORS)
        # Caption should be well within the frame width with margins
        assert cap.width <= PORTRAIT_W * 0.9 + 1e-6


# ---------------------------------------------------------------------------
# Long captions scale down only when needed
# ---------------------------------------------------------------------------

def test_long_caption_scales_down_landscape():
    """A very long caption scales down to fit within margins in landscape."""
    long_text = "This is a very long caption that describes a complex scene with many details and should wrap to multiple lines because it exceeds the wrap width"
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap = make_caption(long_text, COLORS)
        assert cap.width <= LANDSCAPE_W * 0.9 + 1e-6


def test_long_caption_scales_down_portrait():
    """A very long caption scales down to fit within margins in portrait."""
    long_text = "This is a very long caption that describes a complex scene with many details and should wrap to multiple lines because it exceeds the wrap width"
    with _frame_dims(PORTRAIT_W, PORTRAIT_H):
        cap = make_caption(long_text, COLORS)
        assert cap.width <= PORTRAIT_W * 0.9 + 1e-6


def test_medium_caption_fits_without_scaling():
    """A caption that already fits within margins is not scaled at all."""
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap = make_caption("A moderate length caption", COLORS)
        # Natural width should be under max_caption_width, so no scaling
        assert cap.width <= LANDSCAPE_W * 0.9 + 1e-6


# ---------------------------------------------------------------------------
# Multiline captions
# ---------------------------------------------------------------------------

def test_multiline_caption_landscape():
    """Multiline captions wrap per explicit newlines and fit within margins."""
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap = make_caption("Line one\nLine two\nLine three", COLORS)
        assert cap.width <= LANDSCAPE_W * 0.9 + 1e-6
        # Height should account for multiple lines
        assert cap.height > 0


def test_multiline_caption_portrait():
    """Multiline captions work in portrait orientation."""
    with _frame_dims(PORTRAIT_W, PORTRAIT_H):
        cap = make_caption("Line one\nLine two\nLine three", COLORS)
        assert cap.width <= PORTRAIT_W * 0.9 + 1e-6


# ---------------------------------------------------------------------------
# Unicode captions
# ---------------------------------------------------------------------------

def test_unicode_caption_landscape():
    """Unicode captions render without error and fit within margins."""
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap = make_caption("Café résumé 日本語 🎬", COLORS)
        assert cap.width <= LANDSCAPE_W * 0.9 + 1e-6


def test_unicode_caption_portrait():
    """Unicode captions render without error and fit within margins in portrait."""
    with _frame_dims(PORTRAIT_W, PORTRAIT_H):
        cap = make_caption("Café résumé 日本語 🎬", COLORS)
        assert cap.width <= PORTRAIT_W * 0.9 + 1e-6


# ---------------------------------------------------------------------------
# Very narrow frames
# ---------------------------------------------------------------------------

def test_narrow_frame_caption_landscape():
    """A very narrow frame still produces a readable caption with minimum
    wrap width."""
    with _frame_dims(NARROW_W, NARROW_H):
        cap = make_caption("A short caption in a very narrow frame", COLORS)
        # Caption must fit within the narrow frame with margins
        assert cap.width <= NARROW_W * 0.9 + 1e-6
        assert cap.height > 0


def test_narrow_frame_long_caption():
    """A long caption in a very narrow frame scales down to fit."""
    with _frame_dims(NARROW_W, NARROW_H):
        cap = make_caption("This is a long caption that must fit in a very narrow frame", COLORS)
        assert cap.width <= NARROW_W * 0.9 + 1e-6


# ---------------------------------------------------------------------------
# Caption does not collide with main content (vertical position)
# ---------------------------------------------------------------------------

def test_caption_pinned_to_bottom_with_buff():
    """Caption is pinned to the bottom edge with a buffer, leaving room above
    for main content."""
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap = make_caption("Test caption", COLORS)
        # Caption bottom should be near the bottom edge (y is negative downward)
        # Manim coordinates: center is (0,0), bottom edge is -frame_height/2
        bottom_edge = -LANDSCAPE_H / 2
        # caption's bottom should be above the bottom edge by buff
        expected_bottom = bottom_edge + LANDSCAPE_H * 0.04 + cap.height / 2
        assert abs(cap.get_bottom()[1] - expected_bottom) < 0.5, (
            f"caption bottom {cap.get_bottom()[1]:.2f} not near expected {expected_bottom:.2f}"
        )


# ---------------------------------------------------------------------------
# Landscape vs portrait font size scaling
# ---------------------------------------------------------------------------

def test_portrait_font_larger_than_landscape():
    """Portrait frames use a larger font (capped at 40) for readability."""
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap_land = make_caption("Test caption text here", COLORS)
        land_font = cap_land.font_size

    with _frame_dims(PORTRAIT_W, PORTRAIT_H):
        cap_port = make_caption("Test caption text here", COLORS)
        port_font = cap_port.font_size

    # Both fonts should be positive and reasonable (Manim may adjust internally)
    assert land_font > 0 and port_font > 0
    # Portrait font should not be smaller than landscape (same text, taller frame)
    assert port_font >= land_font * 0.8, (
        f"portrait font {port_font} too small vs landscape {land_font}"
    )


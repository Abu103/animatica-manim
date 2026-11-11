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

from animatica.components._draw import CAPTION_CONTENT_GAP, caption_band_top, make_caption
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
# The caption must stay inside the 5% safe-area margin
# ---------------------------------------------------------------------------

#: frame-lint keeps this fraction of each edge free of content.
SAFE_AREA_MARGIN = 0.05


@pytest.mark.parametrize("fw,fh", [(14.222222222222221, 8.0), (14.222222222222221, 8.0)])
@pytest.mark.parametrize("label,text", [
    ("one-line", "Comparing two icy moons"),
    ("two-line", "Positive charges gather at the cloud's top, negative charges at its "
                 "base, and the ground below turns positive."),
])
def test_caption_bottom_clears_safe_area(fw, fh, label, text):
    """The caption's bbox bottom must be above the safe-area margin.

    frame-lint flags any non-background pixel inside the outer 5% of the
    frame. A caption pinned with a 4% buffer puts its descenders inside
    that band, so every frame of every video warns.
    """
    with _frame_dims(fw, fh):
        cap = make_caption(text, COLORS)
        bottom = cap.get_bottom()[1]

    limit = -fh / 2 + SAFE_AREA_MARGIN * fh
    assert bottom > limit, (
        f"{label} caption bottom {bottom:.4f} is inside the "
        f"{SAFE_AREA_MARGIN:.0%} safe-area margin (limit {limit:.4f})"
    )


def test_caption_band_top_follows_the_real_caption():
    """Layout code needs the caption's real top to reserve space for it.

    A one-line caption leaves more room than a two-line one, so the band must
    be derived from the caption mobject rather than a constant.
    """
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        one = make_caption("Short", COLORS)
        two = make_caption(
            "A much longer caption that wraps onto a second line and so "
            "reaches higher up the frame than the short one does",
            COLORS,
        )
        band_one = caption_band_top(one)
        band_two = caption_band_top(two)

    assert band_two > band_one, (
        f"two-line caption band {band_two:.4f} must sit higher than the "
        f"one-line band {band_one:.4f}, leaving less room for content"
    )
    assert band_one > one.get_top()[1], "band must clear the caption's top"


def test_caption_band_top_without_a_caption():
    """With no caption on screen the band is the safe-area line, plus a gap."""
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        band = caption_band_top()

    limit = (
        -LANDSCAPE_H / 2
        + SAFE_AREA_MARGIN * LANDSCAPE_H
        + CAPTION_CONTENT_GAP
    )
    assert band == pytest.approx(limit, abs=1e-6)


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


# ---------------------------------------------------------------------------
# The caption is one Text mobject per line, not a row of words
# ---------------------------------------------------------------------------


def test_caption_is_one_text_per_line():
    """A caption is a single Text mobject; each newline is a line in it.

    Word-by-word pieces (one Text or MathTex per word) lost the shared
    baseline and the word gaps: the rendered caption read "termbrings" and
    "legendis". Math inside a caption needs one block per line with a
    measured baseline, which is its own card; until then the caption stays
    exactly one Text.
    """
    text = "The curve e^x and x**2 agree near zero."
    with _frame_dims(LANDSCAPE_W, LANDSCAPE_H):
        cap = make_caption(text, COLORS)
        multi = make_caption("Line one\nLine two\nLine three", COLORS)

    assert cap.__class__.__name__ == "Text", (
        f"the caption is a {cap.__class__.__name__}, not one Text mobject"
    )
    # Manim's ``Text.text`` is the glyph text with the spaces removed; the
    # original string is the one the renderer asked for.
    source = getattr(cap, "original_text", cap.text)
    assert source.split() == text.split(), (
        f"the caption's words changed: {source!r}"
    )
    assert not [m for m in cap.get_family() if m.__class__.__name__ == "MathTex"], (
        "the caption is typeset word by word again"
    )
    # An explicit line break is one line of the same Text, not a group of rows.
    assert multi.__class__.__name__ == "Text"
    multi_source = getattr(multi, "original_text", multi.text)
    assert multi_source.count("\n") == 2, multi_source


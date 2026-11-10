"""Shared Manim helpers for components: timing budget, text fitting, text-card fallback, warnings."""
from __future__ import annotations

import textwrap
from typing import Any

from animatica.components.theme import ThemeColors

MIN_FONT_SIZE = 32  # Manim font_size units; ~3% of 1080p height
FADE_OUT = 0.4


def warn(scene: Any, message: str) -> None:
    sink = getattr(scene, "warnings", None)
    if sink is not None:
        sink.append(message)


_FONT_CANDIDATES = ("Segoe UI", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans", "Liberation Sans", "Noto Sans")
_FONT_CACHE: list[str | None] = []


def pick_font() -> str | None:
    """First clean sans-serif installed on this machine (None = leave Manim's default)."""
    if not _FONT_CACHE:
        found = None
        try:
            import manimpango
            available = set(manimpango.list_fonts())
            found = next((f for f in _FONT_CANDIDATES if f in available), None)
        except Exception:
            found = None
        _FONT_CACHE.append(found)
    return _FONT_CACHE[0]


def prepare(scene: Any, colors: ThemeColors) -> None:
    scene.camera.background_color = colors.background
    font = pick_font()
    if font:
        try:
            from manim import MarkupText, Text
            Text.set_default(font=font)
            MarkupText.set_default(font=font)
        except Exception:
            pass  # cosmetic only


def wrap(text: str, width: int) -> str:
    """Wrap each line to `width` characters, keeping the caller's own line breaks."""
    out: list[str] = []
    for line in text.split("\n"):
        out.extend(textwrap.wrap(line, width=width) or [""])
    return "\n".join(out)


def fit(
    mobject: Any,
    max_width: float | None = None,
    max_height: float | None = None,
    scale_up: bool = True,
) -> Any:
    """Scale a mobject to fit inside the frame with margins.

    First scales down if the mobject exceeds the frame bounds, then optionally
    scales up proportionally to fill the available space. Content never
    overflows the frame because the up-scale is limited by whichever dimension
    is more constraining.

    Set ``scale_up=False`` to only shrink content that is too large, leaving
    smaller content at its natural size. This is useful for text/math content
    that should keep comfortable side margins rather than expanding to fill
    the frame.
    """
    from manim import config
    max_width = max_width or config.frame_width - 1.0
    max_height = max_height or config.frame_height - 2.4  # bottom band reserved for caption
    if mobject.width > max_width:
        mobject.scale_to_fit_width(max_width)
    if mobject.height > max_height:
        mobject.scale_to_fit_height(max_height)
    # Scale up proportionally to fill the frame when content is smaller than
    # the bounds. Limited by min(scale_w, scale_h) so content never overflows.
    if scale_up:
        scale_w = max_width / mobject.width if mobject.width > 0 else 1.0
        scale_h = max_height / mobject.height if mobject.height > 0 else 1.0
        scale = min(scale_w, scale_h)
        if scale > 1.0:
            mobject.scale(scale)
    return mobject


class Clock:
    """Tracks time spent so a beat takes exactly its declared duration."""

    def __init__(self, scene: Any, total: float) -> None:
        self.scene, self.total, self.used = scene, total, 0.0

    def play(self, *animations: Any, run_time: float) -> None:
        self.scene.play(*animations, run_time=run_time)
        self.used += run_time

    def wait(self, seconds: float) -> None:
        if seconds > 1e-6:
            self.scene.wait(seconds)
            self.used += seconds

    def finish(self, fade_out: float = FADE_OUT) -> None:
        """Hold until the budget minus the fade, then fade everything out."""
        from manim import FadeOut
        if self.used + fade_out > self.total + 0.05:
            warn(self.scene, f"timing: a beat ran {self.used + fade_out - self.total:.1f}s longer than its declared "
                             f"{self.total:.1f}s; captions may drift")
        self.wait(max(0.0, self.total - fade_out - self.used))
        if self.scene.mobjects:
            self.play(*[FadeOut(m) for m in self.scene.mobjects], run_time=fade_out)
        else:
            self.wait(fade_out)
        self.wait(max(0.0, self.total - self.used))


#: Fraction of each frame edge that frame-lint keeps free of content.
SAFE_AREA_MARGIN = 0.05

#: Buffer between the frame's bottom edge and the caption's bottom edge.
#: Must exceed ``SAFE_AREA_MARGIN`` so the caption's descenders stay out of
#: the safe-area band; 0.055 is the smallest value that clears it.
CAPTION_BOTTOM_BUFF = 0.055

#: Gap kept between the caption's top and the bottom of the content above it.
CAPTION_CONTENT_GAP = 0.25


def make_caption(text: str, colors: ThemeColors) -> Any:
    """Burned-in caption pinned to the bottom edge, sized for actual frame dimensions.

    Uses ``config.frame_width`` / ``config.frame_height`` (set by ``manim render
    -r ...``) so caption font and wrap width adapt to portrait (9:16) and
    landscape frames. For a 5.6x10.0 frame the font scales up ~1.8x and the
    wrap width scales down to ~28 chars so the caption stays readable and
    within the safe area.

    The caption is only scaled *down* when it would overflow the frame with
    horizontal margins; short captions are never enlarged to fill the frame,
    which previously made tiny captions unreadably large and edge-to-edge.

    It is pinned clear of the ``SAFE_AREA_MARGIN`` band: a caption closer to
    the edge puts its descenders inside that band, and frame-lint then warns
    about every single frame of the video.
    """
    from manim import DOWN, Text, config

    frame_width = config.frame_width
    frame_height = config.frame_height

    # Baseline: landscape (12.4 x 5.6). Scale font with frame height.
    font_size = 28 * (frame_height / 5.6)
    # Cap at 40 so very tall frames don't produce unreadably large text.
    font_size = min(font_size, 40)
    # Wrap width scales with frame width, but never below 20 chars so very
    # narrow frames still produce readable (if narrow) captions.
    wrap_width = max(20, int(62 * (frame_width / 12.4)))

    cap = Text(wrap(text, wrap_width), font_size=font_size, color=colors.muted, line_spacing=0.8)

    # Only scale down if the caption is too wide for the frame with margins.
    # Never scale up: short captions stay at their natural readable size.
    # 5% horizontal margin on each side keeps captions from touching the edge.
    max_caption_width = frame_width * 0.9
    if cap.width > max_caption_width:
        cap.scale_to_fit_width(max_caption_width)

    cap.to_edge(DOWN, buff=frame_height * CAPTION_BOTTOM_BUFF)
    return cap


def caption_band_top(caption: Any = None) -> float:
    """Y coordinate above which content must stay to leave room for the caption.

    The caption's height depends on how its text wraps, so the band cannot be
    a constant: a one-line caption leaves more room than a two-line one.
    Layout code uses this to decide how much vertical space it may use.

    Pass the real caption mobject (the scene builds one per beat and keeps it
    on ``scene.caption_mobject``) to get its exact top. With no caption on
    screen there is nothing to collide with, but content must still stay out
    of the safe-area band, so the band is the frame's bottom edge plus the
    safe-area margin and a small gap.
    """
    from manim import config

    if caption is not None:
        return caption.get_top()[1] + CAPTION_CONTENT_GAP
    return (
        -config.frame_height / 2
        + SAFE_AREA_MARGIN * config.frame_height
        + CAPTION_CONTENT_GAP
    )


def clear_stage(scene: Any) -> None:
    """Remove everything except the burned-in caption."""
    keep = getattr(scene, "caption_mobject", None)
    for m in list(scene.mobjects):
        if m is not keep:
            scene.remove(m)


def text_card(scene: Any, text: str, colors: ThemeColors, total: float) -> None:
    """Fallback card used when a component fails: shows plain text for `total` seconds."""
    from manim import FadeIn, Text
    clear_stage(scene)
    t = fit(Text(wrap(text, 40), font_size=MIN_FONT_SIZE + 8, color=colors.text))
    clock = Clock(scene, total)
    clock.play(FadeIn(t), run_time=min(0.6, total / 3))
    clock.finish()


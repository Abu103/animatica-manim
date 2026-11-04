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


def fit(mobject: Any, max_width: float | None = None, max_height: float | None = None) -> Any:
    """Scale a mobject down (never up) so it fits inside the frame with margins."""
    from manim import config
    max_width = max_width or config.frame_width - 1.0
    max_height = max_height or config.frame_height - 2.4  # bottom band is reserved for the caption
    if mobject.width > max_width:
        mobject.scale_to_fit_width(max_width)
    if mobject.height > max_height:
        mobject.scale_to_fit_height(max_height)
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


def make_caption(text: str, colors: ThemeColors) -> Any:
    """Burned-in caption pinned to the bottom edge."""
    from manim import DOWN, Text
    cap = Text(wrap(text, 62), font_size=28, color=colors.muted, line_spacing=0.8)
    if cap.width > 12.4:
        cap.scale_to_fit_width(12.4)
    return cap.to_edge(DOWN, buff=0.3)


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


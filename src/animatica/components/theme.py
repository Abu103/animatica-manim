"""Palettes and WCAG contrast math. No Manim import here."""
from __future__ import annotations

from dataclasses import dataclass

from animatica.storyboard.models import Theme

MIN_FONT_PX = 32  # 3% of a 1080p frame height
WCAG_AA = 4.5


@dataclass(frozen=True)
class ThemeColors:
    background: str
    text: str
    accent: str
    accent2: str
    muted: str


PALETTES: dict[str, ThemeColors] = {
    "dark-blue": ThemeColors("#0B0B12", "#FFFFFF", "#38BDF8", "#FBBF24", "#94A3B8"),
    "light": ThemeColors("#FFFFFF", "#0F172A", "#1D4ED8", "#B45309", "#475569"),
    "high-contrast": ThemeColors("#000000", "#FFFFFF", "#FFFF00", "#00FFFF", "#D1D5DB"),
}


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def get_colors(theme: Theme) -> ThemeColors:
    try:
        return PALETTES[theme.palette]
    except KeyError:
        raise ValueError(f"Unknown palette {theme.palette!r}. Valid palettes: {', '.join(sorted(PALETTES))}") from None


"""The template's chrome must not read as content to the frame linter.

A real Windows render of docs/gallery/howto.json produced 25 frame-lint warnings, all traced to
chrome: the corner glows were bright enough to count as "content" (edge_contact, safe_area, and a
mean-luminance low_contrast of ~1.6:1 whenever no text had faded in yet), and the masthead and
footer rule sat inside the 5% safe-area band.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from animatica import frame_lint

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "src" / "animatica" / "backends" / "hyperframes" / "template.html"
).read_text(encoding="utf-8")

STAGE_H = 720
BAND_Y = int(STAGE_H * frame_lint.FrameLintConfig().safe_area_margin)


def _rgb(hex_color: str) -> np.ndarray:
    h = hex_color.lstrip("#")
    return np.array([[[int(h[i:i + 2], 16) for i in (0, 2, 4)]]], dtype=np.uint8)


def _gray(hex_color: str) -> float:
    return float(frame_lint._grayscale(_rgb(hex_color)).mean())


def test_backdrop_glows_stay_below_the_linters_content_threshold():
    bg = re.search(r"--c-bg:\s*(#[0-9a-fA-F]{6})", TEMPLATE).group(1)
    glows = re.findall(r"radial-gradient\([^#]*(#[0-9a-fA-F]{6}) 0%", TEMPLATE)
    assert len(glows) == 2
    for glow in glows:
        assert abs(_gray(glow) - _gray(bg)) < frame_lint._BG_DIFF, (
            f"glow {glow} would be counted as content by frame_lint"
        )


def test_masthead_is_outside_the_top_safe_area_band():
    top = int(re.search(r"\.masthead \{[^}]*?top:\s*(\d+)px", TEMPLATE, re.S).group(1))
    assert top >= BAND_Y


def test_footer_is_outside_the_bottom_safe_area_band():
    for rule in (r"\.footer-rule \{[^}]*?bottom:\s*(\d+)px", r"\.footer-progress \{[^}]*?bottom:\s*(\d+)px"):
        bottom = int(re.search(rule, TEMPLATE, re.S).group(1))
        assert bottom >= BAND_Y

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


# ---------------------------------------------------------------------------
# Bundled typography
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402

from animatica.backends.hyperframes import compose  # noqa: E402

FONTS_DIR = Path(compose.__file__).parent / "fonts"

#: sha256 of the fontsource/dejavu-sans@5.3.0 latin woff2 files we ship. A font swap must be deliberate.
FONT_SHA256 = {
    "dejavu-sans-400.woff2": "c3c7ca00b4538cc10906a5d4d921aab2369b2bee781168ef2ca695f3a5805760",
    "dejavu-sans-700.woff2": "77fef6ca55dd03f7a12bc113181bda99062de681c84fd27355c6dec26cd9263c",
}


def test_every_font_the_template_references_is_bundled_and_pinned():
    refs = re.findall(r'url\("fonts/([^"]+)"\)', TEMPLATE)
    assert sorted(refs) == sorted(FONT_SHA256)
    for name, digest in FONT_SHA256.items():
        assert hashlib.sha256((FONTS_DIR / name).read_bytes()).hexdigest() == digest


def test_the_font_licence_ships_with_the_fonts():
    text = (FONTS_DIR / "DEJAVU-LICENSE.txt").read_text(encoding="utf-8")
    assert "Bitstream" in text and "Permission is hereby granted" in text


def test_fonts_are_copied_next_to_the_composition(tmp_path):
    import json

    from animatica.backends.hyperframes.plan import plan_storyboard
    from animatica.storyboard.models import Storyboard

    gallery = Path(__file__).resolve().parent.parent / "docs" / "gallery" / "howto.json"
    plan = plan_storyboard(Storyboard.model_validate(json.loads(gallery.read_text())), captions=True)
    compose.write_composition(plan, tmp_path)
    for name, digest in FONT_SHA256.items():
        assert hashlib.sha256((tmp_path / "fonts" / name).read_bytes()).hexdigest() == digest


def test_fonts_are_declared_in_package_data():
    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "backends/hyperframes/fonts/*" in pyproject

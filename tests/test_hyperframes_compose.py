"""Tests for the deterministic HyperFrames composer.

Everything here runs without Node, a browser, Manim or ffmpeg. The security
tests matter most: they pin the boundary between "storyboard text is data" and
"text becomes markup or code".
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from animatica.backends.hyperframes.compose import (
    COLOR_CLASSES,
    COMPOSITION_ID,
    content_hash,
    render_html,
    write_composition,
)
from animatica.backends.hyperframes.plan import BeatPlan, Line, Plan, plan_storyboard
from animatica.storyboard.models import Storyboard

GALLERY = Path(__file__).resolve().parent.parent / "docs" / "gallery"


def howto_plan():
    storyboard = Storyboard.model_validate(json.loads((GALLERY / "howto.json").read_text()))
    return plan_storyboard(storyboard)


def html_for(scenes, title="t"):
    storyboard = Storyboard.model_validate({"version": "1", "title": title, "scenes": scenes})
    return render_html(plan_storyboard(storyboard))


def script_bodies(html: str) -> str:
    return "".join(re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S))


class _Audit(HTMLParser):
    """Collect tags, attribute names and text, to prove what a parser actually sees."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(name for name, _value in attrs)

    def handle_data(self, data):
        self.text.append(data)


def audit(html: str) -> _Audit:
    parser = _Audit()
    parser.feed(html)
    return parser


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_stage_and_sections_encode_the_plan_timeline():
    html = render_html(howto_plan())

    assert f'data-composition-id="{COMPOSITION_ID}"' in html
    assert 'data-duration="10"' in html
    assert 'data-width="1280"' in html and 'data-height="720"' in html
    assert html.count('class="beat clip"') == 2
    assert 'id="scene-1-beat-1"' in html and 'id="scene-2-beat-1"' in html
    assert 'data-start="0" data-duration="3"' in html
    assert 'data-start="3" data-duration="7"' in html


def test_every_plan_line_is_rendered_once():
    plan = howto_plan()
    html = render_html(plan)

    assert html.count('class="line ') == plan.line_count()
    for beat in plan.beats:
        for line in beat.lines:
            assert line.text in html


def test_geometry_and_reveal_times_come_from_the_plan():
    html = render_html(howto_plan())

    # title: centred at x=328.96, 64px bold, revealed 0.15 s into the beat
    assert "left:328.96px" in html
    assert "font-size:64px" in html
    assert 'data-reveal="0.15"' in html
    # steps: numbers at the margin, text offset by STEP_NUMBER_W, 4-step cadence
    assert "left:80px" in html
    assert "left:136px" in html
    assert 'data-reveal="4.9"' in html


def test_caption_is_in_the_caption_band():
    html = render_html(howto_plan())
    captions = re.findall(r'<div class="line c-muted l-caption" data-reveal="[^"]+" style="([^"]+)"', html)
    assert len(captions) == 2
    for style in captions:
        top = float(re.search(r"top:([\d.]+)px", style).group(1))
        assert 584 <= top <= 640


def test_section_ids_are_unique_and_stable():
    ids = re.findall(r'<section id="([^"]+)"', render_html(howto_plan()))
    assert ids == ["scene-1-beat-1", "scene-2-beat-1"]
    assert len(set(ids)) == len(ids)


def test_template_placeholders_are_all_substituted():
    html = render_html(howto_plan())
    assert "__ANIMATICA_" not in html


def test_no_network_references():
    """A composition must render offline: no CDN, no imports, no webfont fetch."""
    html = render_html(howto_plan())
    assert "http://" not in html and "https://" not in html
    assert "@import" not in html
    assert "src=" not in html


def test_no_inline_event_handlers():
    html = render_html(howto_plan())
    assert not re.search(r"\son[a-z]+\s*=", html)


# ---------------------------------------------------------------------------
# Boundary: storyboard text is data, never markup or code
# ---------------------------------------------------------------------------


HOSTILE = '</script><img src=x onerror=alert(1)><svg onload=alert(2)>" onclick="x'

def test_hostile_text_is_escaped_everywhere():
    html = html_for(
        [
            {"beats": [
                {"component": "title_card", "params": {"title": HOSTILE, "subtitle": HOSTILE},
                 "caption": HOSTILE},
            ]},
            {"beats": [
                {"component": "steps_list", "params": {"items": [HOSTILE, "ok"]}, "caption": HOSTILE},
            ]},
        ],
        title=HOSTILE,
    )

    seen = audit(html)
    assert "img" not in seen.tags and "svg" not in seen.tags
    assert not [name for name in seen.attrs if name.startswith("on")]
    assert "&lt;img" in html
    assert "&quot;" in html  # the quote-in-attribute attempt is neutralised
    # The hostile string is still visible to a reader, as inert text.
    assert any(HOSTILE in chunk for chunk in seen.text)


def test_storyboard_text_never_reaches_the_script_block():
    html = html_for(
        [{"beats": [{"component": "title_card", "params": {"title": "SECRET-TITLE-MARKER"}}]}],
        title="SECRET-STORYBOARD-MARKER",
    )
    body = script_bodies(html)
    assert "SECRET-TITLE-MARKER" not in body
    assert "SECRET-STORYBOARD-MARKER" not in body


def test_unicode_survives_the_round_trip(tmp_path):
    html = html_for(
        [{"beats": [{"component": "title_card", "params": {"title": "Café — ünïcode 日本語"}}]}]
    )
    assert "Café — ünïcode 日本語" in html
    storyboard = Storyboard.model_validate(
        {"version": "1", "title": "Café", "scenes": [
            {"beats": [{"component": "title_card", "params": {"title": "Café — ünïcode 日本語"}}]}]}
    )
    path = write_composition(plan_storyboard(storyboard), tmp_path)
    assert "Café — ünïcode 日本語" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_composition_is_byte_identical_across_calls():
    first = render_html(howto_plan())
    second = render_html(howto_plan())

    assert first == second
    assert content_hash(first) == content_hash(second)
    assert len(content_hash(first)) == 64


def test_different_storyboards_hash_differently():
    a = render_html(howto_plan())
    b = html_for([{"beats": [{"component": "title_card", "params": {"title": "Something else"}}]}])
    assert content_hash(a) != content_hash(b)


def test_write_composition_writes_index_html(tmp_path):
    path = write_composition(howto_plan(), tmp_path / "out")

    assert path == tmp_path / "out" / "index.html"
    assert path.read_text(encoding="utf-8") == render_html(howto_plan())
    assert "\r\n" not in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_equations_are_plain_text_until_math_typesetting_lands():
    html = html_for(
        [{"beats": [{"component": "equation", "params": {"latex": [r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}"]}}]}]
    )
    assert "\u221a" in html  # √
    assert "\\sqrt" not in html


def test_unknown_colour_token_is_rejected():
    bad = Plan(
        title="bad",
        beats=(
            BeatPlan(
                scene=1, index=1, component="title_card", start=0.0, duration=3.0,
                lines=(Line("x", 100.0, 100.0, 50.0, 40.0, 30, color="neon"),),
            ),
        ),
    )
    with pytest.raises(ValueError, match="colour token"):
        render_html(bad)
    assert set(COLOR_CLASSES) == {"text", "muted", "accent"}


def test_empty_plan_is_rejected():
    with pytest.raises(ValueError, match="no beats"):
        render_html(Plan(title="empty", beats=()))

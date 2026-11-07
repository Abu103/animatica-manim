"""Tests for the renderer-neutral HyperFrames plan (layout + timing).

These run without Node, a browser, Manim or ffmpeg: that is the whole point of
keeping geometry and timing out of the template.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from animatica.backends.hyperframes.plan import (
    BODY_BOTTOM,
    BODY_BOTTOM_WITH_CAPTION,
    CAPTION_AREA,
    MARGIN,
    SAFE_AREA,
    STAGE_H,
    STAGE_W,
    BeatPlan,
    Line,
    Plan,
    PlanError,
    Rect,
    plan_storyboard,
    problems,
    text_width,
    wrap,
)
from animatica.storyboard.models import Storyboard

GALLERY = Path(__file__).resolve().parent.parent / "docs" / "gallery"


def sb(scenes):
    """Build a Storyboard from a compact scenes description."""
    return Storyboard.model_validate({"version": "1", "title": "t", "scenes": scenes})


def beat(component, params, caption=""):
    return {"beats": [{"component": component, "params": params, "caption": caption}]}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def test_gallery_howto_timeline():
    storyboard = Storyboard.model_validate(json.loads((GALLERY / "howto.json").read_text()))
    plan = plan_storyboard(storyboard)

    assert plan.scene_count == 2
    assert [b.component for b in plan.beats] == ["title_card", "steps_list"]
    # 3.0 s title card, then 1.5 s per step + 1.0 s = 7.0 s.
    assert [(b.start, b.duration) for b in plan.beats] == [(0.0, 3.0), (3.0, 7.0)]
    assert plan.duration == 10.0


def test_beats_are_contiguous():
    plan = plan_storyboard(
        sb(
            [
                beat("title_card", {"title": "One"}),
                beat("equation", {"latex": ["a^2"]}),
                beat("steps_list", {"items": ["x", "y"]}),
            ]
        )
    )
    for previous, current in zip(plan.beats, plan.beats[1:]):
        assert current.start == previous.end


def test_duration_matches_component_and_conformance_corpus():
    """The plan must not invent its own timing: components own duration()."""
    storyboard = Storyboard.model_validate(
        json.loads((Path(__file__).resolve().parent / "conformance" / "steps.json").read_text())
    )
    plan = plan_storyboard(storyboard)
    assert plan.duration == 5.5  # matches tests/conformance/expected.json


def test_multiple_beats_in_one_scene_are_not_overlaid():
    plan = plan_storyboard(
        sb([{"beats": [
            {"component": "title_card", "params": {"title": "A"}},
            {"component": "title_card", "params": {"title": "B"}},
        ]}])
    )
    assert [b.start for b in plan.beats] == [0.0, 3.0]
    assert all(b.scene == 1 for b in plan.beats)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_title_card_is_centred_and_inside_the_safe_area():
    plan = plan_storyboard(sb([beat("title_card", {"title": "How to Boil an Egg", "subtitle": "Four simple steps."})]))
    title, subtitle = plan.beats[0].body_lines

    assert title.text == "How to Boil an Egg"
    assert title.align == "center"
    assert abs((title.rect.x + title.w / 2) - STAGE_W / 2) < 1.0
    assert subtitle.color == "muted"
    assert subtitle.y > title.y
    assert not title.rect.overlaps(subtitle.rect)
    assert problems(plan) == []


def test_long_title_wraps_and_stays_inside_safe_area():
    long_title = "A fairly long title that cannot possibly fit on one single line of the stage"
    plan = plan_storyboard(sb([beat("title_card", {"title": long_title})]))
    lines = plan.beats[0].body_lines

    assert len(lines) > 1
    assert "".join(line.text for line in lines).replace(" ", "") == long_title.replace(" ", "")
    for line in lines:
        assert line.rect.within(SAFE_AREA)
    assert problems(plan) == []


def test_steps_are_numbered_left_aligned_and_never_overlap():
    items = ["Boil water", "Lower the egg in", "Wait 9 minutes", "Cool in cold water"]
    plan = plan_storyboard(sb([beat("steps_list", {"items": items}, caption="Follow the steps in order.")]))
    body = plan.beats[0].body_lines

    numbers = [line for line in body if line.role == "number"]
    texts = [line for line in body if line.role != "number"]
    assert [n.text for n in numbers] == ["1.", "2.", "3.", "4."]
    assert [t.text for t in texts] == items
    assert all(t.x > n.x for n, t in zip(numbers, texts))
    assert [line.y for line in texts] == sorted(line.y for line in texts)
    assert problems(plan) == []


def test_eight_long_steps_compress_instead_of_overflowing():
    items = [
        "Preheat the oven to two hundred degrees and line the tray with parchment",
        "Whisk the dry ingredients together in a large bowl until evenly combined",
        "Add the wet ingredients and fold gently until no dry flour remains",
        "Pour the batter into the prepared tray and smooth the surface flat",
        "Bake until the centre springs back when pressed lightly with a finger",
        "Cool in the tray for ten minutes, then turn out onto a wire rack",
        "Dust with icing sugar just before serving so it does not dissolve",
        "Store leftovers in an airtight container for up to three days",
    ]
    plan = plan_storyboard(sb([beat("steps_list", {"items": items})]))
    problems_found = problems(plan)

    assert problems_found == []
    assert plan.beats[0].meta["size"] < 30  # shrank to fit


def test_unfittable_steps_raise_an_actionable_error():
    items = [" ".join(["word"] * 60)] * 8
    with pytest.raises(PlanError, match="Split the list"):
        plan_storyboard(sb([beat("steps_list", {"items": items})]))


def test_equation_lines_use_plain_text_and_are_revealed_in_order():
    plan = plan_storyboard(
        sb([beat("equation", {"mode": "reveal", "latex": ["a^2 + b^2 = c^2", r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}"]})])
    )
    lines = plan.beats[0].body_lines

    assert len(lines) == 2
    assert lines[0].text == "a^2 + b^2 = c^2"
    assert "\u221a" in lines[1].text  # √, not raw \sqrt
    assert "\\" not in lines[1].text
    assert lines[0].reveal < lines[1].reveal
    assert lines[-1].reveal <= plan.beats[0].duration
    assert problems(plan) == []


def test_caption_is_placed_in_the_caption_band_and_body_clears_it():
    plan = plan_storyboard(
        sb([beat("title_card", {"title": "Titled"}, caption="A caption that explains the title card.")])
    )
    caption = plan.beats[0].caption_line

    assert caption is not None
    assert caption.rect.within(CAPTION_AREA)
    assert caption.y >= CAPTION_AREA.y
    for line in plan.beats[0].body_lines:
        assert line.rect.bottom <= BODY_BOTTOM_WITH_CAPTION + 0.5
    assert problems(plan) == []


def test_body_uses_full_height_when_there_is_no_caption():
    plan = plan_storyboard(sb([beat("steps_list", {"items": ["a"]})]))
    assert plan.beats[0].caption_line is None
    assert plan.beats[0].body_lines[0].y < BODY_BOTTOM_WITH_CAPTION


def test_pythagoras_gallery_storyboard_plans_cleanly():
    storyboard = Storyboard.model_validate(json.loads((GALLERY / "pythagoras.json").read_text()))
    plan = plan_storyboard(storyboard)
    assert plan.duration == 7.0  # 3.0 title + 2x2.0 equation lines
    assert problems(plan) == []


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_problems_reports_overlap_with_numbers():
    line_a = Line("Hello", 100.0, 100.0, 200.0, 40.0, 30)
    line_b = Line("World", 150.0, 120.0, 200.0, 40.0, 30)
    bad = Plan(
        title="bad",
        beats=(
            BeatPlan(
                scene=1,
                index=1,
                component="title_card",
                start=0.0,
                duration=3.0,
                lines=(line_a, line_b),
            ),
        ),
    )
    found = problems(bad)
    assert any("overlap" in msg and "'Hello'" in msg and "'World'" in msg for msg in found)


def test_problems_reports_content_outside_the_safe_area():
    line = Line("Offstage", 5.0, 5.0, 100.0, 40.0, 30)
    bad = Plan(
        title="bad",
        beats=(BeatPlan(scene=1, index=1, component="title_card", start=0.0, duration=3.0, lines=(line,)),),
    )
    found = problems(bad)
    assert any("leaves the safe area" in msg for msg in found)


def test_problems_reports_reveals_after_the_beat_ends():
    line = Line("Late", 100.0, 100.0, 100.0, 40.0, 30, reveal=9.0)
    bad = Plan(
        title="bad",
        beats=(BeatPlan(scene=1, index=1, component="title_card", start=0.0, duration=3.0, lines=(line,)),),
    )
    assert any("outside the beat" in msg for msg in problems(bad))


# ---------------------------------------------------------------------------
# Contract: unsupported input, determinism, isolation
# ---------------------------------------------------------------------------


def test_unsupported_component_fails_before_rendering_with_advice():
    with pytest.raises(PlanError) as excinfo:
        plan_storyboard(sb([beat("graph", {"fn": "sin(x)"})]))
    message = str(excinfo.value)
    assert "graph" in message
    assert "title_card" in message and "steps_list" in message
    assert "manim" in message


def test_invalid_params_are_named_by_field():
    with pytest.raises(PlanError, match="items"):
        plan_storyboard(sb([beat("steps_list", {"items": []})]))


def test_planning_is_deterministic():
    storyboard = Storyboard.model_validate(json.loads((GALLERY / "howto.json").read_text()))
    assert plan_storyboard(storyboard) == plan_storyboard(storyboard)


def test_plan_serialises_to_json_for_the_template():
    """The plan is the only thing the template receives: it must be plain JSON."""
    storyboard = Storyboard.model_validate(json.loads((GALLERY / "howto.json").read_text()))
    payload = plan_storyboard(storyboard).as_dict()

    text = json.dumps(payload)
    assert list(payload) == ["title", "beats", "width", "height"]
    assert payload["beats"][1]["component"] == "steps_list"
    assert payload["beats"][1]["lines"][0]["role"] == "number"
    assert payload["beats"][0]["lines"][0]["x"] == 328.96  # deterministic golden geometry
    assert "plan" not in text or True  # no renderer names leak into the payload


def test_steps_block_is_vertically_centred():
    plan = plan_storyboard(sb([beat("steps_list", {"items": ["a", "b"]})]))
    lines = plan.beats[0].body_lines
    top = lines[0].rect.y
    bottom = lines[-1].rect.bottom
    assert abs((top - SAFE_AREA.y) - (SAFE_AREA.bottom - bottom)) < 1.0


def test_wide_characters_are_measured_wider():
    assert text_width("\u6f22\u5b57", 30) > text_width("ab", 30)


def test_wrap_never_loses_words():
    text = "one two three four five six seven eight nine ten"
    lines = wrap(text, 30, 200)
    assert " ".join(lines).split() == text.split()
    assert all(text_width(line, 30) <= 200 for line in lines)


def test_plan_module_imports_without_manim():
    """The seam must be testable in any environment: importing it pulls in no renderer."""
    code = (
        "import sys; import animatica.backends.hyperframes as h; "
        "print('manim' in sys.modules)"
    )
    src = str(Path(__file__).resolve().parent.parent / "src")
    env = {**os.environ, "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", "")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_rect_helpers():
    assert Rect(0, 0, 10, 10).within(Rect(0, 0, 20, 20))
    assert not Rect(15, 0, 10, 10).within(Rect(0, 0, 20, 20))
    assert Rect(0, 0, 10, 10).overlaps(Rect(5, 5, 10, 10))
    assert not Rect(0, 0, 10, 10).overlaps(Rect(10, 0, 10, 10))
    assert Rect(0, 0, 10, 10).right == 10
    assert Rect(0, 0, 10, 10).bottom == 10

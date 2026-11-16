"""T34b/T34c: the model is asked to write a separate spoken line per beat, and lint checks it."""
from __future__ import annotations

import json

from animatica.ai.base import AIProvider
from animatica.ai.prompt import build_fill_prompt, build_prompt
from animatica.ai.repair import generate_storyboard, generate_storyboard_two_stage
from animatica.components.registry import default_registry
from animatica.pipeline import cache_variant
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Beat, Scene, Storyboard


class _Stub(AIProvider):
    name = "stub"
    model = "m"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def generate(self, prompt, schema):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def _sb(*beats: Beat) -> Storyboard:
    return Storyboard(title="t", scenes=[Scene(beats=list(beats))])


def _eq(narration: str, caption: str = "Squares of the legs add up.") -> Beat:
    return Beat(component="equation", params={"mode": "reveal", "latex": ["a^2+b^2=c^2"]},
                caption=caption, narration=narration)


# ---- prompt ----

def test_default_prompt_does_not_mention_narration():
    assert "narration" not in build_prompt("pythagoras", default_registry())


def test_narrate_prompt_asks_for_separate_spoken_text():
    p = build_prompt("pythagoras", default_registry(), narrate=True)
    assert '"narration"' in p
    assert "spoken" in p and "caption" in p
    assert "250 characters" in p
    # the example the model copies must itself show a narration that differs from the caption
    ex = json.loads(p.split("Example output:\n")[1].split("\n")[0])
    beats = [b for s in ex["scenes"] for b in s["beats"]]
    assert all(b["narration"] and b["narration"] != b["caption"] for b in beats)
    Storyboard.model_validate(ex)


def test_narrate_prompt_keeps_repair_errors():
    p = build_prompt("x", default_registry(), ["boom"], narrate=True)
    assert "boom" in p and '"narration"' in p


def test_fill_prompt_narrate_flag():
    sc = {"beats": [{"component": "equation", "intent": "state it"}]}
    assert "narration" not in build_fill_prompt("x", default_registry(), sc)
    assert '"narration"' in build_fill_prompt("x", default_registry(), sc, narrate=True)


def test_generate_storyboard_threads_narrate():
    reply = json.dumps({"version": "1", "title": "t", "scenes": [{"beats": [
        {"component": "title_card", "params": {"title": "T"}, "caption": "Hi", "narration": "Welcome in."}]}]})
    prov = _Stub([reply])
    sb = generate_storyboard("x", prov, default_registry(), narrate=True)
    assert sb.scenes[0].beats[0].narration == "Welcome in."
    assert '"narration"' in prov.prompts[0]


def test_two_stage_threads_narrate():
    outline = json.dumps({"version": "1", "title": "t", "scenes": [
        {"beats": [{"component": "title_card", "intent": "open"}]}]})
    fill = json.dumps({"version": "1", "title": "t", "scenes": [{"beats": [
        {"component": "title_card", "params": {"title": "T"}, "caption": "Hi", "narration": "Welcome in."}]}]})
    prov = _Stub([outline, fill])
    generate_storyboard_two_stage("x", prov, default_registry(), narrate=True)
    assert '"narration"' not in prov.prompts[0]  # the outline stage has no text to speak yet
    assert '"narration"' in prov.prompts[1]


def test_cache_variant_only_changes_when_narrating():
    reg = default_registry()
    plain = cache_variant(_Stub([]), False, reg)
    assert cache_variant(_Stub([]), False, reg, False) == plain
    assert cache_variant(_Stub([]), False, reg, True) != plain


# ---- lint ----

def test_lint_drops_production_narration_and_keeps_caption():
    sb, notes = lint_storyboard(_sb(_eq("This scene shows the equation.")))
    assert sb.scenes[0].beats[0].narration == ""
    assert sb.scenes[0].beats[0].caption == "Squares of the legs add up."
    assert any("narration describes the production" in n for n in notes)


def test_lint_keeps_good_narration_silently():
    good = "Square the two short sides, add them, and you get the square of the long side."
    sb, notes = lint_storyboard(_sb(_eq(good)))
    assert sb.scenes[0].beats[0].narration == good
    assert not [n for n in notes if "narration" in n]


def test_lint_warns_about_symbols_a_voice_reads_literally():
    _, notes = lint_storyboard(_sb(_eq("a^2 + b^2 = c^2 is the rule.")))
    assert any("symbols" in n and "^" in n for n in notes)


def test_lint_warns_about_very_long_narration():
    _, notes = lint_storyboard(_sb(_eq("word " * 55)))  # 275 chars, over the 250 the prompt asks for
    assert any("is long" in n for n in notes)


def test_lint_warns_when_narration_mentions_a_ball_the_component_lacks():
    _, notes = lint_storyboard(_sb(_eq("Watch the ball bounce along.")))
    assert any("ball/hop" in n for n in notes)


def test_lint_ignores_beats_without_narration():
    _, notes = lint_storyboard(_sb(_eq("")))
    assert not [n for n in notes if "narration" in n]

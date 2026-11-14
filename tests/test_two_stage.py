import json

import pytest

from animatica.ai.base import StoryboardGenerationError
from animatica.ai.repair import generate_storyboard_two_stage
from animatica.components.registry import default_registry

OUTLINE = {
    "version": "1",
    "title": "Fibonacci",
    "scenes": [
        {"beats": [{"component": "title_card", "intent": "introduce the series"}]},
        {"beats": [{"component": "bounce_sequence", "intent": "ball hops over terms 0..5",
                    "params_hint": {"title": "Terms 0 to 5", "values": [0, 1, 1, 2, 3, 5]}}]},
    ],
}


def fill_for(component, params):
    return {"version": "1", "title": "Fibonacci",
            "scenes": [{"beats": [{"component": component, "params": params, "caption": "c"}]}]}


class TwoStageProvider:
    """Returns the outline on call 1, then one fill per scene in order."""
    name = "two"

    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, schema: dict) -> str:
        self.calls.append(prompt)
        n = len(self.calls)
        if n == 1:
            return json.dumps(OUTLINE)
        if n == 2:
            return json.dumps(fill_for("title_card", {"title": "Fibonacci"}))
        return json.dumps(fill_for("bounce_sequence", {"title": "Terms 0 to 5", "values": [0, 1, 1, 2, 3, 5]}))


class FlakyFillProvider(TwoStageProvider):
    name = "flaky"

    def generate(self, prompt, schema):
        self.calls.append(prompt)
        n = len(self.calls)
        if n == 1:
            return json.dumps(OUTLINE)
        if n == 2:  # first fill attempt: invalid params -> retried alone
            return json.dumps(fill_for("title_card", {"title": 123}))
        if n == 3:
            return json.dumps(fill_for("title_card", {"title": "Fibonacci"}))
        return json.dumps(fill_for("bounce_sequence", {"title": "T", "values": [0, 1, 1, 2, 3, 5]}))


class BadOutlineProvider:
    name = "bo"
    def __init__(self):
        self.calls = 0
    def generate(self, prompt, schema):
        self.calls += 1
        return "garbage"


def test_two_stage_happy_path():
    p = TwoStageProvider()
    sb = generate_storyboard_two_stage("fibonacci with a ball", p, default_registry())
    assert sb.title == "Fibonacci"
    assert len(sb.scenes) == 2
    assert sb.scenes[1].beats[0].component == "bounce_sequence"
    assert len(p.calls) == 1 + 2  # outline + one fill per scene


def test_two_stage_retries_one_scene_alone():
    p = FlakyFillProvider()
    sb = generate_storyboard_two_stage("x", p, default_registry())
    assert sb.scenes[0].beats[0].params["title"] == "Fibonacci"


def test_two_stage_bad_outline_raises_after_retries():
    p = BadOutlineProvider()
    with pytest.raises(StoryboardGenerationError):
        generate_storyboard_two_stage("x", p, default_registry(), max_retries=2)
    assert p.calls == 3


def test_outline_schema_validated():
    class WrongComponentOutline:
        name = "wc"
        def __init__(self): self.calls = 0
        def generate(self, prompt, schema):
            self.calls += 1
            bad = {"version": "1", "title": "t", "scenes": [{"beats": [{"component": "not_a_component", "intent": "x"}]}]}
            return json.dumps(bad)
    p = WrongComponentOutline()
    with pytest.raises(StoryboardGenerationError) as exc:
        generate_storyboard_two_stage("x", p, default_registry(), max_retries=1)
    assert any("not_a_component" in e for e in exc.value.errors)

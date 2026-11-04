import pytest

from animatica.ai.base import StoryboardGenerationError
from animatica.ai.repair import generate_storyboard
from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard

GOOD_SB = Storyboard.model_validate(
    {
        "version": "1",
        "title": "Test",
        "scenes": [
            {
                "beats": [
                    {
                        "component": "title_card",
                        "params": {"title": "Test"},
                    }
                ]
            }
        ],
    }
)


class GoodProvider:
    name = "good"

    def generate(self, prompt: str, schema: dict) -> str:
        return "```json\n" + GOOD_SB.model_dump_json() + "\n```"


class BadThenGoodProvider:
    name = "btg"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt: str, schema: dict) -> str:
        self.calls += 1
        if self.calls == 1:
            return "not json at all"
        return "```json\n" + GOOD_SB.model_dump_json() + "\n```"


class AlwaysBadProvider:
    name = "bad"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt: str, schema: dict) -> str:
        self.calls += 1
        return "not json"


def test_good_provider_one_call():
    sb = generate_storyboard("make a title card", GoodProvider(), default_registry())
    assert sb.title == "Test"


def test_bad_then_good_two_calls():
    p = BadThenGoodProvider()
    sb = generate_storyboard("x", p, default_registry())
    assert p.calls == 2
    assert sb.title == "Test"


def test_always_bad_three_calls_then_error():
    p = AlwaysBadProvider()
    with pytest.raises(StoryboardGenerationError):
        generate_storyboard("x", p, default_registry(), max_retries=2)
    assert p.calls == 3


def test_feedback_at_most_six_lines():
    calls = []

    class EmptyScenesProvider:
        name = "es"
        def generate(self, prompt, schema):
            calls.append(prompt)
            return "```json\n{\"version\":\"1\",\"title\":\"t\",\"scenes\":[]}\n```"

    p = EmptyScenesProvider()
    with pytest.raises(StoryboardGenerationError):
        generate_storyboard("x", p, default_registry(), max_retries=2)
    last = calls[-1]
    # feedback section holds at most the first 6 validation errors
    error_block = last.split("Errors:")[-1] if "Errors:" in last else last
    lines = [l for l in error_block.splitlines() if l.strip()]
    assert len(lines) <= 6


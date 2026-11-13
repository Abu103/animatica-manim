"""T17: offline regression gate.

Ten real model outputs, recorded once with `animatica eval --save-dir`, are replayed through
parse -> validate -> lint -> duration with no network. A storyboard that stops validating, starts
drawing lint warnings, or changes length/shape beyond the thresholds in `thresholds.json` fails here.

Refresh the fixtures after a deliberate change: record a new run (`animatica eval --models nim
--prompts tests/reference_prompts.txt --max-retries 0 --save-dir <dir>`), copy the chosen files'
`prompt`, `provider`, `model` and last `responses` entry into `tests/fixtures/eval_replay/`, and
update `thresholds.json` to match.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from animatica.ai.base import StoryboardGenerationError
from animatica.ai.repair import generate_storyboard
from animatica.components.registry import default_registry
from animatica.eval import _duration
from animatica.storyboard.lint import lint_storyboard

FIXTURES = Path(__file__).parent / "fixtures" / "eval_replay"
THRESHOLDS = json.loads((FIXTURES / "thresholds.json").read_text(encoding="utf-8"))
NAMES = sorted(THRESHOLDS)


class _Replay:
    name = "replay"
    model = "replay"

    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def generate(self, prompt, schema):
        self.calls += 1
        return self.text


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def gate_problems(prompt: str, response: str, limits: dict) -> list[str]:
    """Replay one recorded response; return what regressed (empty list = pass)."""
    registry = default_registry()
    provider = _Replay(response)
    try:
        sb = generate_storyboard(prompt, provider, registry, max_retries=0)
    except StoryboardGenerationError as exc:
        return [f"no longer valid on the first try: {exc.errors[:2]}"]
    sb, notes = lint_storyboard(sb)
    problems: list[str] = []
    components = [b.component for s in sb.scenes for b in s.beats]
    if components != limits["components"]:
        problems.append(f"components changed: {components} != {limits['components']}")
    if len(notes) > limits["max_warnings"]:
        problems.append(f"{len(notes)} lint warnings, allowed {limits['max_warnings']}: {notes}")
    duration = _duration(sb, registry)
    if not limits["min_duration"] <= duration <= limits["max_duration"]:
        problems.append(f"duration {duration:.1f}s outside {limits['min_duration']}-{limits['max_duration']}s")
    return problems


def test_there_are_ten_recorded_outputs_and_each_has_thresholds():
    on_disk = sorted(p.name for p in FIXTURES.glob("*.json") if p.name != "thresholds.json")
    assert on_disk == NAMES
    assert len(NAMES) >= 10


@pytest.mark.parametrize("name", NAMES)
def test_recorded_output_still_passes_the_gate(name):
    rec = _load(name)
    assert gate_problems(rec["prompt"], rec["response"], THRESHOLDS[name]) == []


@pytest.mark.parametrize("name", NAMES)
def test_deleting_a_field_from_a_fixture_fails_the_gate(name):
    """The card's proof: a damaged fixture must not slip through."""
    rec = _load(name)
    data = json.loads(rec["response"])
    del data["scenes"][0]["beats"][0]["params"]
    problems = gate_problems(rec["prompt"], json.dumps(data), THRESHOLDS[name])
    assert problems and "no longer valid" in problems[0]


def test_changing_the_component_fails_the_gate():
    name = NAMES[0]
    rec = _load(name)
    limits = dict(THRESHOLDS[name], components=["table"])
    assert any("components changed" in p for p in gate_problems(rec["prompt"], rec["response"], limits))


def test_tight_duration_limits_fail_the_gate():
    name = NAMES[0]
    rec = _load(name)
    limits = dict(THRESHOLDS[name], min_duration=500, max_duration=600)
    assert any("duration" in p for p in gate_problems(rec["prompt"], rec["response"], limits))

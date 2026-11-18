"""N2: the outline prompt's 8-beat cap is enforced without burning retries.

A model that returns 15 beats in one scene used to fail _Outline validation
("scenes.0.beats: at most 8 items, not 15"). The outline is split into
consecutive scenes of at most MAX_BEATS and filled normally.
"""
from __future__ import annotations

import json

from animatica.ai.prompt import build_outline_prompt
from animatica.ai.repair import generate_storyboard_two_stage
from animatica.components.registry import default_registry
from animatica.storyboard.models import MAX_BEATS


class _Provider:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, prompt: str, schema: dict) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0)


def _outline(beats_per_scene: list[int]) -> str:
    scenes = []
    for count in beats_per_scene:
        scenes.append({"beats": [
            {"component": "title_card", "intent": f"beat {i}"} for i in range(count)
        ]})
    return json.dumps({"version": "1", "title": "T", "scenes": scenes})


def _fill(count: int) -> str:
    return json.dumps({"version": "1", "title": "T", "scenes": [{
        "beats": [{"component": "title_card", "params": {"title": f"B{i}"},
                   "caption": f"slide {i}"} for i in range(count)]
    }]})


def test_outline_prompt_states_the_eight_beat_cap():
    prompt = build_outline_prompt("topic", default_registry())
    lower = prompt.lower()
    assert "max 8 beats per scene" in lower or "at most 8 beats per scene" in lower


def test_fifteen_beat_scene_is_split_not_rejected():
    # nim repro: scenes.0.beats: at most 8 items, not 15
    provider = _Provider(_outline([15]), _fill(8), _fill(7))
    sb = generate_storyboard_two_stage("topic", provider, default_registry())
    assert [len(scene.beats) for scene in sb.scenes] == [8, 7]
    assert all(len(scene.beats) <= MAX_BEATS for scene in sb.scenes)
    assert len(provider.prompts) == 3  # one outline + two fills, no retry


def test_split_then_truncate_when_the_scene_cap_would_break():
    # 12 scenes x 9 beats would split into 18 scenes (> MAX_SCENES): keep
    # each original scene capped at 8 instead of inventing extra scenes.
    provider = _Provider(_outline([9] * 12), *[_fill(8)] * 12)
    sb = generate_storyboard_two_stage("topic", provider, default_registry())
    assert len(sb.scenes) == 12
    assert all(len(scene.beats) == 8 for scene in sb.scenes)

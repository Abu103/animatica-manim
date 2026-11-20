"""O2: over-long narration/captions are clamped locally, not retried.

A beat with narration over 300 chars is cut at the last sentence boundary
under the cap, a warning is recorded in report.json, and no provider retry
is burned on a pure length violation (nim repro:
"scenes.0.beats.6.narration at most 300 chars").
"""
from __future__ import annotations

import json
from typing import ClassVar

import animatica.pipeline as pipeline
from animatica.ai.repair import generate_storyboard, generate_storyboard_two_stage, repair_with_facts
from animatica.backends.base import RenderResult
from animatica.components.registry import default_registry
from animatica.storyboard.clamp import clamp_lengths
from animatica.storyboard.models import MAX_TEXT, Storyboard


def _sb_json(narration: str, caption: str = "hi") -> str:
    return json.dumps({"version": "1", "title": "T", "scenes": [{"beats": [
        {"component": "title_card", "params": {"title": "B"},
         "caption": caption, "narration": narration}
    ]}]})


LONG = "First sentence is short. " + ("long words follow. " * 40)


class _Provider:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.model = "m"
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, prompt: str, schema: dict) -> str:
        self.calls += 1
        return self.replies.pop(0)


def _fake_backend(monkeypatch):
    class FakeBackend:
        name = "fake"
        version = "9.9"
        supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]

        def capabilities(self):
            return self.supported_capabilities

        def render(self, sb, out_dir, opts):
            video = out_dir / "video.mp4"
            video.write_bytes(b"x")
            return RenderResult(video=video, durations=[1.0], warnings=[], stage_times={})

    monkeypatch.setattr(pipeline, "default_backends", lambda: {"fake": FakeBackend()})


def test_clamp_cuts_at_a_sentence_boundary():
    data = json.loads(_sb_json(LONG))
    result, notes = clamp_lengths(data)
    text = result["scenes"][0]["beats"][0]["narration"]
    assert len(text) <= MAX_TEXT
    assert text.endswith(".")
    assert any("scene 0 beat 0 narration" in note for note in notes)


def test_clamp_caption_and_no_boundary_fallback():
    data = json.loads(_sb_json("x" * (MAX_TEXT + 50), caption="y" * (MAX_TEXT + 50)))
    result, notes = clamp_lengths(data)
    beat = result["scenes"][0]["beats"][0]
    assert len(beat["narration"]) == MAX_TEXT
    assert len(beat["caption"]) == MAX_TEXT
    assert len(notes) == 2


def test_single_stage_does_not_retry_a_length_violation():
    provider = _Provider(_sb_json(LONG))
    notes: list[str] = []
    sb = generate_storyboard("topic", provider, default_registry(), notes=notes)
    assert provider.calls == 1
    assert len(sb.scenes[0].beats[0].narration) <= MAX_TEXT
    assert any("narration" in note for note in notes)


def test_two_stage_fill_does_not_retry_a_length_violation():
    outline = json.dumps({"version": "1", "title": "T", "scenes": [{"beats": [
        {"component": "title_card", "intent": "i"}]}]})
    provider = _Provider(outline, _sb_json(LONG))
    notes: list[str] = []
    sb = generate_storyboard_two_stage("topic", provider, default_registry(), notes=notes)
    assert provider.calls == 2  # one outline, one fill
    assert len(sb.scenes[0].beats[0].narration) <= MAX_TEXT
    assert any("narration" in note for note in notes)


def test_repair_clamps_and_reports_a_note():
    bad = Storyboard.model_validate(json.loads(
        '{"version":"1","title":"T","scenes":[{"beats":['
        '{"component":"stat_callout","params":{"value":"12%","label":"g"},'
        '"caption":"grew 40%"}]}]}'))
    reply = json.dumps({"version": "1", "title": "T", "scenes": [{"beats": [
        {"component": "stat_callout", "params": {"value": "12%", "label": "g"},
         "caption": "grew 12%", "narration": LONG}]}]})
    provider = _Provider(reply)
    sb, info = repair_with_facts("topic", bad, provider, default_registry())
    assert provider.calls == 1
    assert len(sb.scenes[0].beats[0].narration) <= MAX_TEXT
    assert any("narration" in note for note in info["clamps"])


def test_from_storyboard_is_clamped_and_warns(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "get_provider", lambda name, cfg: None)
    _fake_backend(monkeypatch)
    source = tmp_path / "sb.json"
    source.write_text(_sb_json(LONG), encoding="utf-8")
    out = tmp_path / "out"
    pipeline.make_video(storyboard_path=source, out_dir=out,
                        provider="auto", backend="fake", frame_lint=False)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert any("shortened" in w for w in report["warnings"])
    written = json.loads((out / "storyboard.json").read_text(encoding="utf-8"))
    assert len(written["scenes"][0]["beats"][0]["narration"]) <= MAX_TEXT


def test_two_stage_note_names_the_final_scene():
    outline = json.dumps({"version": "1", "title": "T", "scenes": [
        {"beats": [{"component": "title_card", "intent": "a"}]},
        {"beats": [{"component": "title_card", "intent": "b"}]},
    ]})
    provider = _Provider(outline, _sb_json("short"), _sb_json(LONG))
    notes: list[str] = []
    generate_storyboard_two_stage("topic", provider, default_registry(), notes=notes)
    assert any("scene 1 beat 0 narration" in note for note in notes)


def test_rejected_attempt_leaves_no_stale_clamp_note():
    rejected = json.dumps({"version": "1", "title": "T", "scenes": [{"beats": [
        {"component": "nope", "params": {}, "narration": LONG}]}]})
    provider = _Provider(rejected, _sb_json("short"))
    notes: list[str] = []
    generate_storyboard("topic", provider, default_registry(), notes=notes)
    assert notes == []


def test_degraded_narration_removes_its_clamp_note():
    bad = Storyboard.model_validate(json.loads(
        '{"version":"1","title":"T","scenes":[{"beats":['
        '{"component":"stat_callout","params":{"value":"12%","label":"g"},'
        '"caption":"grew 40%","narration":"grew 40%"}]}]}'))
    reply = json.dumps({"version": "1", "title": "T", "scenes": [{"beats": [
        {"component": "stat_callout", "params": {"value": "12%", "label": "g"},
         "caption": "grew 12%", "narration": "grew 40%. " * 30}]}]})
    provider = _Provider(reply)
    sb, info = repair_with_facts("topic", bad, provider, default_registry())
    assert sb.scenes[0].beats[0].narration == ""
    assert not [note for note in info["clamps"] if "narration" in note]

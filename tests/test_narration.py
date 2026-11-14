"""Narration core: synthesize() and narrate_storyboard(), no real Piper binary needed.

``run``/``which`` are injected the same way ``doctor``/``latex_check`` do it,
so these tests never touch a real subprocess.
"""
from __future__ import annotations

import pytest

from animatica import narration
from animatica.components.registry import default_registry
from animatica.pipeline import beat_text
from animatica.storyboard.models import Beat, Scene, Storyboard


def _sb(captions: list[str]) -> Storyboard:
    return Storyboard(
        title="t",
        scenes=[Scene(beats=[Beat(component="title_card", params={"title": "hi"}, caption=c)]) for c in captions],
    )


class FakeCompleted:
    def __init__(self, returncode: int = 0, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr


def test_beat_text_prefers_caption_over_fallback():
    registry = default_registry()
    comp = registry.get("title_card")
    beat = Beat(component="title_card", params={"title": "hi"}, caption="spoken line")
    assert beat_text(beat, comp) == "spoken line"


def test_beat_text_falls_back_when_no_caption():
    registry = default_registry()
    comp = registry.get("title_card")
    beat = Beat(component="title_card", params={"title": "hi"}, caption="")
    params = comp.Params.model_validate(beat.params)
    assert beat_text(beat, comp) == comp.fallback_text(params)


def test_synthesize_rejects_unchecked_voice(tmp_path):
    with pytest.raises(narration.NarrationUnavailable, match="allowlist"):
        narration.synthesize(
            "hi",
            tmp_path / "out.wav",
            voice="some-unvetted-voice",
            which=lambda _name: "/usr/bin/piper",
        )


def test_synthesize_fails_closed_without_piper_on_path(tmp_path):
    with pytest.raises(narration.NarrationUnavailable, match="doctor --fix"):
        narration.synthesize("hi", tmp_path / "out.wav", which=lambda _name: None)


def test_synthesize_fails_closed_without_voice_model(tmp_path):
    with pytest.raises(narration.NarrationUnavailable, match="voice model is not installed"):
        narration.synthesize(
            "hi",
            tmp_path / "out.wav",
            which=lambda _name: "/usr/bin/piper",
            voice_model_path=None,
        )
    missing = tmp_path / "does-not-exist.onnx"
    with pytest.raises(narration.NarrationUnavailable, match="voice model is not installed"):
        narration.synthesize(
            "hi",
            tmp_path / "out.wav",
            which=lambda _name: "/usr/bin/piper",
            voice_model_path=missing,
        )


def test_synthesize_runs_piper_and_returns_the_path(tmp_path):
    model = tmp_path / "en_US-ljspeech-medium.onnx"
    model.write_text("fake model", encoding="utf-8")
    out = tmp_path / "beat.wav"
    seen = {}

    def fake_run(cmd, input=None, capture_output=None, text=None):  # noqa: A002
        seen["cmd"] = cmd
        seen["input"] = input
        out.write_bytes(b"RIFF....WAVEfake")
        return FakeCompleted(returncode=0)

    result = narration.synthesize(
        "a ball hops along the terms",
        out,
        voice_model_path=model,
        run=fake_run,
        which=lambda _name: "/usr/bin/piper",
    )
    assert result == out
    assert out.exists()
    assert seen["input"] == "a ball hops along the terms"
    assert seen["cmd"][0] == "/usr/bin/piper"
    assert str(model) in seen["cmd"]


def test_synthesize_raises_on_piper_failure(tmp_path):
    model = tmp_path / "model.onnx"
    model.write_text("fake", encoding="utf-8")

    def failing_run(cmd, input=None, capture_output=None, text=None):  # noqa: A002
        return FakeCompleted(returncode=1, stderr="some piper internal error\nlast line of detail")

    with pytest.raises(narration.NarrationUnavailable, match="last line of detail"):
        narration.synthesize(
            "hi",
            tmp_path / "out.wav",
            voice_model_path=model,
            run=failing_run,
            which=lambda _name: "/usr/bin/piper",
        )


def test_narrate_storyboard_matches_beat_durations_shape(tmp_path):
    sb = _sb(["one", "two"])
    registry = default_registry()
    calls = []

    def fake_synthesize(text, out_path, voice=narration.DEFAULT_VOICE, voice_model_path=None):
        calls.append((text, out_path))
        return out_path

    result = narration.narrate_storyboard(sb, registry, tmp_path, synthesize_fn=fake_synthesize)
    assert len(result) == len(sb.scenes) == 2
    assert all(len(scene_paths) == 1 for scene_paths in result)
    assert [c[0] for c in calls] == ["one", "two"]
    assert result[0][0] == tmp_path / "scene00_beat00.wav"
    assert result[1][0] == tmp_path / "scene01_beat00.wav"


def test_narrate_storyboard_uses_fallback_text_when_caption_is_empty(tmp_path):
    sb = _sb([""])
    registry = default_registry()
    comp = registry.get("title_card")
    expected = comp.fallback_text(comp.Params.model_validate({"title": "hi"}))
    seen_text = {}

    def fake_synthesize(text, out_path, voice=narration.DEFAULT_VOICE, voice_model_path=None):
        seen_text["text"] = text
        return out_path

    narration.narrate_storyboard(sb, registry, tmp_path, synthesize_fn=fake_synthesize)
    assert seen_text["text"] == expected

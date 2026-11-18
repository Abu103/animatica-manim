"""Merge fixes F3/F4: provider errors in the repair loop, narration-only degradation."""
import json
from typing import ClassVar

import animatica.pipeline as pipeline
from animatica.ai.repair import repair_with_facts
from animatica.backends.base import RenderResult
from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard

REGISTRY = default_registry()
BAD_CAPTION = "This graph shows the frequency domain of the wave."
BAD_NARRATION = "The frequency spectrum appears here."
GOOD = "This graph plots a sine wave over time."


def _sb(caption, narration):
    return Storyboard.model_validate({
        "version": "1",
        "title": "Sine",
        "scenes": [{"beats": [{
            "component": "graph",
            "params": {"fn": "sin(x)", "x_range": [0, 6], "y_range": [-2, 2]},
            "caption": caption,
            "narration": narration,
        }]}],
    })


class ExplodingProvider:
    name = "explode"
    model = "m"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, schema):
        self.calls += 1
        raise RuntimeError("provider offline")


def test_provider_error_stops_retries_and_records_repair_error():
    p = ExplodingProvider()
    sb, info = repair_with_facts("topic", _sb(BAD_CAPTION, BAD_NARRATION), p, REGISTRY)
    assert p.calls == 1  # no retry after a provider error
    assert "repair_error" in info
    assert "provider offline" in info["repair_error"]
    assert sb.scenes[0].beats[0].caption == BAD_CAPTION  # current storyboard kept


class BadThenExplodeProvider:
    name = "btx"
    model = "m"

    def __init__(self, bad):
        self.bad = bad
        self.calls = 0

    def generate(self, prompt, schema):
        self.calls += 1
        if self.calls == 1:
            return "```json\n" + self.bad.model_dump_json() + "\n```"
        raise RuntimeError("provider offline on repair")


def _fake_backend(monkeypatch):
    class FakeBackend:
        name = "fake"
        version = "9.9"
        supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]

        def capabilities(self):
            return list(self.supported_capabilities)

        def render(self, sb, out_dir, opts):
            video = out_dir / "video.mp4"
            video.write_bytes(b"x")
            return RenderResult(video=video, durations=[1.0], warnings=[], stage_times={"total": 1.0})

    monkeypatch.setattr(pipeline, "default_backends", lambda: {"fake": FakeBackend()})


def test_make_video_warns_on_repair_error_and_writes_report(monkeypatch, tmp_path):
    provider = BadThenExplodeProvider(_sb(BAD_CAPTION, BAD_NARRATION))
    monkeypatch.setattr(pipeline, "get_provider", lambda name, cfg: provider)
    _fake_backend(monkeypatch)

    out = tmp_path / "out"
    result = pipeline.make_video(
        prompt="zz repair error", out_dir=out, provider="btx",
        backend="fake", frame_lint=False,
    )
    assert any(w.startswith("verify: ") and "repair" in w for w in result.warnings), result.warnings
    assert (out / "report.json").is_file()
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert any("repair error" in w for w in report["warnings"]), report["warnings"]
    assert report["verification"]["sent_back"] == 0


class NeverCalledProvider:
    name = "never"
    model = "m"

    def generate(self, prompt, schema):
        raise AssertionError("no send-back when max_verify_retries=0")


def test_caption_only_error_keeps_narration():
    sb, info = repair_with_facts(
        "topic", _sb(BAD_CAPTION, GOOD), NeverCalledProvider(), REGISTRY,
        max_verify_retries=0,
    )
    assert sb.scenes[0].beats[0].narration == GOOD
    assert info["degraded"] == []


def test_narration_error_blanks_narration():
    sb, info = repair_with_facts(
        "topic", _sb(GOOD, BAD_NARRATION), NeverCalledProvider(), REGISTRY,
        max_verify_retries=0,
    )
    assert sb.scenes[0].beats[0].narration == ""
    assert info["degraded"] == [[0, 0]]

"""Merge fix F5: mechanical fixes only for fresh model output."""
import json
from typing import ClassVar

import animatica.pipeline as pipeline
from animatica.backends.base import RenderResult
from animatica.storyboard.models import Storyboard, dump_storyboard, load_storyboard


def _clipped_sb():
    return Storyboard.model_validate({
        "version": "1",
        "title": "Clip",
        "scenes": [{"beats": [{
            "component": "graph",
            "params": {"fn": "x**2", "x_range": [-2, 2], "y_range": [0, 1]},
            "caption": "A parabola.",
        }]}],
    })


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


def test_from_storyboard_is_not_fixed(monkeypatch, tmp_path):
    _fake_backend(monkeypatch)
    src = tmp_path / "sb.json"
    dump_storyboard(_clipped_sb(), src)
    out = tmp_path / "out"
    pipeline.make_video(storyboard_path=src, out_dir=out, backend="fake", frame_lint=False)

    written = load_storyboard(out / "storyboard.json")
    assert list(written.scenes[0].beats[0].params["y_range"]) == [0, 1]
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["verification"]["fixed"] == 0
    assert report["verification"]["fixes"] == []


class ClippedProvider:
    name = "clipped"
    model = "m"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, schema):
        self.calls += 1
        return "```json\n" + _clipped_sb().model_dump_json() + "\n```"


def test_fresh_model_storyboard_is_fixed_and_recorded(monkeypatch, tmp_path):
    provider = ClippedProvider()
    monkeypatch.setattr(pipeline, "get_provider", lambda name, cfg: provider)
    _fake_backend(monkeypatch)

    out = tmp_path / "out"
    pipeline.make_video(
        prompt="zz f5 clipped graph", out_dir=out, provider="clipped",
        backend="fake", frame_lint=False,
    )

    written = load_storyboard(out / "storyboard.json")
    assert list(written.scenes[0].beats[0].params["y_range"]) == [-0.4, 4.4]
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["verification"]["fixed"] == 1
    fixes = report["verification"]["fixes"]
    assert len(fixes) == 1
    assert fixes[0]["before"] == [0, 1]
    assert fixes[0]["after"] == [-0.4, 4.4]

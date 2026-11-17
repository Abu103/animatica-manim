"""V2b: facts-based repair loop in the make pipeline (fake provider only)."""
import json
from typing import ClassVar

import animatica.pipeline as pipeline
from animatica.backends.base import RenderResult
from animatica.storyboard.models import Storyboard, dump_storyboard

BAD_CAPTION = "This graph shows the frequency domain of the wave."
BAD_NARRATION = "The frequency spectrum appears here."
GOOD_CAPTION = "This graph plots a sine wave over time."
GOOD_NARRATION = "The curve repeats as x grows."


def _sb(caption, narration):
    return Storyboard.model_validate(
        {
            "version": "1",
            "title": "Sine",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "graph",
                            "params": {
                                "fn": "sin(x)",
                                "x_range": [0, 6],
                                "y_range": [-2, 2],
                            },
                            "caption": caption,
                            "narration": narration,
                        }
                    ]
                }
            ],
        }
    )


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
            return RenderResult(
                video=video, durations=[1.0], warnings=[], stage_times={"total": 1.0}
            )

    monkeypatch.setattr(pipeline, "default_backends", lambda: {"fake": FakeBackend()})


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, *storyboards):
        self.queue = list(storyboards)
        self.calls = []

    def generate(self, prompt, schema):
        self.calls.append(prompt)
        sb = self.queue.pop(0) if self.queue else self.queue_default
        return "```json\n" + sb.model_dump_json() + "\n```"


def _install(monkeypatch, provider):
    monkeypatch.setattr(pipeline, "get_provider", lambda name, cfg: provider)
    _fake_backend(monkeypatch)


def _report(out):
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def _written(out):
    return pipeline.load_storyboard(out / "storyboard.json")


def test_verify_retry_is_sent_back_through_existing_error_channel(monkeypatch, tmp_path):
    provider = FakeProvider(_sb(BAD_CAPTION, BAD_NARRATION), _sb(GOOD_CAPTION, GOOD_NARRATION))
    provider.queue_default = _sb(GOOD_CAPTION, GOOD_NARRATION)
    _install(monkeypatch, provider)

    out = tmp_path / "out"
    labels = []
    pipeline.make_video(
        prompt="zz repair loop domain check",
        out_dir=out,
        provider="fake",
        backend="fake",
        frame_lint=False,
        on_progress=lambda event: labels.append(event.label),
    )

    # 1 initial generation + exactly 1 verify retry (it passed on the retry).
    assert len(provider.calls) == 2
    # The retry used build_prompt's existing errors channel with beat, claim
    # sentence and the computed fact texts.
    retry = provider.calls[1]
    assert "scene 0 beat 0 caption:" in retry
    assert BAD_CAPTION in retry
    assert "the code computed:" in retry
    assert "graph draws y against x" in retry

    beat = _written(out).scenes[0].beats[0]
    assert beat.caption == GOOD_CAPTION
    assert beat.narration == GOOD_NARRATION
    v = _report(out)["verification"]
    assert v["sent_back"] == 1
    assert v["failed"] == 0
    assert any("Sent back 1 finding" in lab for lab in labels)

    # Cache holds the final (post-loop) storyboard, not the rejected first answer.
    cached = list((out / ".animatica_cache").glob("*.json"))
    assert len(cached) == 1
    assert GOOD_CAPTION in cached[0].read_text(encoding="utf-8")


def test_always_failing_verify_degrades_narration_after_two_retries(monkeypatch, tmp_path):
    provider = FakeProvider(
        _sb(BAD_CAPTION, BAD_NARRATION),
        _sb(BAD_CAPTION, BAD_NARRATION),
        _sb(BAD_CAPTION, BAD_NARRATION),
    )
    provider.queue_default = _sb(BAD_CAPTION, BAD_NARRATION)
    _install(monkeypatch, provider)

    out = tmp_path / "out"
    result = pipeline.make_video(
        prompt="zz repair loop always fails",
        out_dir=out,
        provider="fake",
        backend="fake",
        frame_lint=False,
    )

    # 1 initial generation + 2 verify retries, then degrade; run still completes.
    assert len(provider.calls) == 3
    assert any(w.startswith("verify:") for w in result.warnings)
    beat = _written(out).scenes[0].beats[0]
    assert beat.narration == ""  # degraded: speak the caption instead
    assert beat.caption == BAD_CAPTION  # captions are never rewritten
    v = _report(out)["verification"]
    assert v["sent_back"] == 2
    assert v["failed"] >= 1
    assert v["degraded"] == [[0, 0]]

    cached = list((out / ".animatica_cache").glob("*.json"))
    assert len(cached) == 1
    assert '"narration": ""' in cached[0].read_text(encoding="utf-8")


def test_from_storyboard_is_never_sent_back_or_degraded(monkeypatch, tmp_path):
    provider = FakeProvider()
    provider.queue_default = _sb(GOOD_CAPTION, GOOD_NARRATION)
    _install(monkeypatch, provider)

    src = tmp_path / "bad.json"
    dump_storyboard(_sb(BAD_CAPTION, BAD_NARRATION), src)
    out = tmp_path / "out"
    pipeline.make_video(
        storyboard_path=src, out_dir=out, backend="fake", frame_lint=False
    )

    assert provider.calls == []  # never handed to the model
    beat = _written(out).scenes[0].beats[0]
    assert beat.narration == BAD_NARRATION  # never degraded
    assert beat.caption == BAD_CAPTION
    v = _report(out)["verification"]
    assert v["sent_back"] == 0
    assert v["failed"] >= 1  # still a finding, warn only


def test_template_storyboard_is_never_sent_back_or_degraded(monkeypatch, tmp_path):
    provider = FakeProvider()
    provider.queue_default = _sb(GOOD_CAPTION, GOOD_NARRATION)
    _install(monkeypatch, provider)

    out = tmp_path / "out"
    pipeline.make_video(
        prompt="make a title card about hello",
        out_dir=out,
        backend="fake",
        frame_lint=False,
    )
    assert provider.calls == []
    v = _report(out)["verification"]
    assert v["sent_back"] == 0

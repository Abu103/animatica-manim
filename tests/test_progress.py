"""Progress events must describe work that actually happened, never a guess."""
from __future__ import annotations

from pathlib import Path

import pytest

from animatica.backends.base import RenderOptions, RenderResult
from animatica.pipeline import make_video
from animatica.progress import ProgressTracker
from animatica.components.registry import default_registry


# ---------------------------------------------------------------------------
# ProgressTracker
# ---------------------------------------------------------------------------


def test_announce_keeps_the_amount_of_work_unknown():
    events = []
    tracker = ProgressTracker(events.append, post_units=1)

    tracker.announce("storyboard", "resolving storyboard")

    assert len(events) == 1
    event = events[0]
    assert (event.stage, event.done, event.total) == ("storyboard", 0, 0)


def test_backend_scale_plus_post_units_is_the_total():
    events = []
    tracker = ProgressTracker(events.append, post_units=2)

    tracker.backend("scene 1/3: rendering", 0, 3)
    tracker.backend("scene 2/3: done", 2, 3)

    assert [e.total for e in events] == [5, 5]
    assert [e.done for e in events] == [0, 2]


def test_advance_counts_post_processing_without_overshooting():
    events = []
    tracker = ProgressTracker(events.append, post_units=2)

    tracker.backend("merging 1 scene(s)", 1, 1)
    tracker.advance("transcode", "re-encoding")
    tracker.advance("captions", "writing captions and report")
    tracker.advance("captions", "one too many")

    assert tracker.total == 3
    assert [e.done for e in events] == [1, 2, 3, 3]  # clamped, not 4
    assert tracker.done == 3


def test_finish_is_idempotent_and_lands_on_100_percent():
    events = []
    tracker = ProgressTracker(events.append, post_units=1)

    tracker.backend("scene 1/1: done", 1, 1)
    tracker.finish("done: video.mp4")
    tracker.finish("done again")

    assert len(events) == 2
    assert events[-1].finished is True
    assert events[-1].done == events[-1].total == 2


def test_finish_without_any_scale_reports_only_what_happened():
    events = []
    tracker = ProgressTracker(events.append, post_units=1)

    tracker.advance("captions", "writing captions and report")
    tracker.finish()

    assert events[-1].total == events[-1].done == 1
    assert events[-1].finished is True


def test_no_callback_is_harmless():
    tracker = ProgressTracker(None, post_units=1)

    tracker.announce("storyboard", "x")
    tracker.backend("scene 1/1: done", 1, 1)
    tracker.advance("captions", "y")
    tracker.finish()

    assert tracker.finished is True


# ---------------------------------------------------------------------------
# make_video wiring
# ---------------------------------------------------------------------------


class RecordingBackend:
    """Reports one unit per scene, like the manim backend does."""

    name = "recording"
    version = "0"
    supported_capabilities: list[str] = []

    def capabilities(self) -> list[str]:
        caps: set[str] = set()
        registry = default_registry()
        for name in registry.names():
            caps.update(getattr(registry.get(name).__class__, "required_capabilities", []))
        return sorted(caps)

    def render(self, sb, out_dir: Path, opts: RenderOptions) -> RenderResult:  # noqa: ANN001
        n = len(sb.scenes)
        assert opts.progress is not None, "pipeline must hand the backend a reporter"
        for i in range(n):
            opts.progress(f"scene {i + 1}/{n}: rendering", i, n)
        opts.progress(f"merging {n} scene(s)", n, n)
        video = Path(out_dir) / "video.mp4"
        video.write_bytes(b"fake")
        return RenderResult(video=video, durations=[1.0] * n, warnings=[], stage_times={})


@pytest.fixture()
def recording_backend(monkeypatch):
    from animatica import pipeline

    monkeypatch.setattr(pipeline, "resolve_backend", lambda name: RecordingBackend())
    return RecordingBackend


def test_make_video_reports_real_units_then_finishes(tmp_path, recording_backend):
    events = []

    make_video(
        "make a title card about Hello",  # offline template: no model, no manim
        out_dir=tmp_path,
        preview=True,
        on_progress=events.append,
    )

    assert events[0].stage == "storyboard" and events[0].total == 0

    render_events = [e for e in events if e.stage == "render"]
    assert render_events, "the backend's units must reach the caller"
    scenes = max(e.total for e in render_events) - 1  # minus the captions/report unit
    assert scenes >= 1
    assert all(e.total == scenes + 1 for e in render_events)

    # done only ever grows, and the run ends exactly at the total
    assert [e.done for e in events] == sorted(e.done for e in events)
    last = events[-1]
    assert last.finished is True
    assert last.done == last.total
    assert [e.stage for e in events].count("captions") == 1


def test_transcode_and_lint_add_their_own_units(tmp_path, recording_backend, monkeypatch):
    """Opt-in steps are counted only when the user asked for them."""
    from animatica import pipeline

    class Enc:
        name = "libx264"

    monkeypatch.setattr(pipeline, "probe_encoders", lambda: [Enc()])
    monkeypatch.setattr(pipeline, "pick_encoder", lambda name, infos: Enc())

    class Result:
        def __init__(self, path):
            self.path = path
            self.warning = None

    monkeypatch.setattr(pipeline, "transcode", lambda src, dst, enc: Result(src))
    monkeypatch.setattr(pipeline, "lint_video", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "lint_result_to_warnings", lambda res: [])

    events = []
    make_video(
        "make a title card about Hello",
        out_dir=tmp_path,
        preview=True,
        encoder="libx264",
        frame_lint=True,
        on_progress=events.append,
    )

    stages = [e.stage for e in events]
    assert "transcode" in stages and "lint" in stages and "captions" in stages
    last = events[-1]
    assert last.finished and last.done == last.total

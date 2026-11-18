"""V2a: mechanical (meaning-preserving) fixes to a verified storyboard."""
import json
from typing import ClassVar

import animatica.pipeline as pipeline
from animatica.backends.base import RenderResult
from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard, dump_storyboard, load_storyboard
from animatica.verify.fix import apply_fixes

REGISTRY = default_registry()
CAPTION = "A caption that must never be rewritten."
NARRATION = "A narration that must never be rewritten."


def _graph_sb(fn, x_range, y_range):
    return Storyboard.model_validate(
        {
            "version": "1",
            "title": "T",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "graph",
                            "params": {"fn": fn, "x_range": list(x_range), "y_range": list(y_range)},
                            "caption": CAPTION,
                            "narration": NARRATION,
                        }
                    ]
                }
            ],
        }
    )


def test_clipped_graph_y_range_is_widened_from_unclipped_samples():
    # Computed with sample_function(parse_function("x**2"), (-2, 2), 400) WITHOUT
    # y_range: 400 finite samples, min 2.5125e-05, max 4.0, span 3.99997.
    # 10% padding = 0.399997 -> round to 2 dp -> (-0.4, 4.4).
    sb = _graph_sb("x**2", (-2, 2), (0, 1))
    fixed, fixes = apply_fixes(sb, REGISTRY)
    assert len(fixes) == 1
    assert fixes[0].beat == (0, 0)
    assert fixes[0].before == [0, 1]
    assert fixes[0].after == [-0.4, 4.4]
    beat = fixed.scenes[0].beats[0]
    assert list(beat.params["y_range"]) == [-0.4, 4.4]
    assert beat.caption == CAPTION
    assert beat.narration == NARRATION


def test_asymptote_is_left_as_a_finding():
    # tan(x) on (-1.5, 1.5): unclipped span 28.2028, 10x the per-side room of
    # y_range (-2, 2) is 20 -> the needed window is too big, leave it alone.
    sb = _graph_sb("tan(x)", (-1.5, 1.5), (-2, 2))
    fixed, fixes = apply_fixes(sb, REGISTRY)
    assert fixes == []
    assert list(fixed.scenes[0].beats[0].params["y_range"]) == [-2, 2]


def test_apply_fixes_is_idempotent():
    sb = _graph_sb("x**2", (-2, 2), (0, 1))
    fixed, first = apply_fixes(sb, REGISTRY)
    assert first
    again, second = apply_fixes(fixed, REGISTRY)
    assert second == []
    assert list(again.scenes[0].beats[0].params["y_range"]) == [-0.4, 4.4]


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
                video=video,
                durations=[1.0],
                warnings=[],
                stage_times={"total": 1.0},
            )

    monkeypatch.setattr(pipeline, "default_backends", lambda: {"fake": FakeBackend()})


def test_pipeline_does_not_mechanically_fix_a_from_storyboard(tmp_path, monkeypatch):
    # F5 supersedes the old "--from is fixed" contract: only fresh model output
    # is mechanically fixed. --from is verified for warnings only.
    _fake_backend(monkeypatch)
    src = tmp_path / "sb.json"
    dump_storyboard(_graph_sb("x**2", (-2, 2), (0, 1)), src)

    out = tmp_path / "out"
    pipeline.make_video(
        storyboard_path=src, out_dir=out, backend="fake", frame_lint=False
    )
    written = load_storyboard(out / "storyboard.json")
    assert list(written.scenes[0].beats[0].params["y_range"]) == [0, 1]
    assert written.scenes[0].beats[0].caption == CAPTION
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["verification"]["fixed"] == 0
    assert report["verification"]["fixes"] == []

    # A --from re-run of the written storyboard gives the same result, zero fixes.
    out2 = tmp_path / "out2"
    pipeline.make_video(
        storyboard_path=out / "storyboard.json", out_dir=out2, backend="fake", frame_lint=False
    )
    report2 = json.loads((out2 / "report.json").read_text(encoding="utf-8"))
    assert report2["verification"]["fixed"] == 0

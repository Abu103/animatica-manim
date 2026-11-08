import json
import pytest
from pathlib import Path
from typing import ClassVar

from animatica.backends.base import RenderBackend, RenderOptions, RenderResult
from animatica.report import StageTimer, write_report


def test_stage_timer_records_stages_and_total():
    t = StageTimer()
    with t.stage("a"):
        pass
    with t.stage("b"):
        pass
    assert set(t.stages) == {"a", "b"}
    assert t.total == t.stages["a"] + t.stages["b"]
    assert t.total >= 0.0


def test_write_report_produces_stages_warnings_and_scene_durations(tmp_path):
    p = tmp_path / "report.json"
    write_report(p, {"a": 1.0, "b": 2.0}, ["w1", "w2"], scene_durations=[1.5, 2.0])
    data = json.loads(p.read_text(encoding="utf-8"))
    assert set(data) == {"stages", "warnings", "scene_durations"}
    assert data["stages"] == {"a": 1.0, "b": 2.0}
    assert data["warnings"] == ["w1", "w2"]
    assert data["scene_durations"] == [1.5, 2.0]


def test_preview_frame_requires_scene_durations(tmp_path):
    """preview_frame must raise an actionable error if report.json lacks scene_durations."""
    from animatica.pipeline import preview_frame

    (tmp_path / "v.mp4").write_bytes(b"fake video")
    with pytest.raises(ValueError, match="no scene durations"):
        preview_frame(tmp_path / "v.mp4", [], 0, 0.0)


def test_preview_frame_scene_index_out_of_range(tmp_path):
    """preview_frame must reject scene_index >= len(scene_durations)."""
    from animatica.pipeline import preview_frame

    (tmp_path / "v.mp4").write_bytes(b"fake video")
    with pytest.raises(ValueError, match="out of range"):
        preview_frame(tmp_path / "v.mp4", [1.0], 1, 0.0)


def test_preview_frame_negative_t(tmp_path):
    """preview_frame must reject negative t."""
    from animatica.pipeline import preview_frame

    (tmp_path / "v.mp4").write_bytes(b"fake video")
    with pytest.raises(ValueError, match="t must be >= 0"):
        preview_frame(tmp_path / "v.mp4", [1.0], 0, -0.5)


def test_preview_frame_t_beyond_scene_duration(tmp_path):
    """preview_frame must reject t beyond scene duration."""
    from animatica.pipeline import preview_frame

    (tmp_path / "v.mp4").write_bytes(b"fake video")
    with pytest.raises(ValueError, match="beyond scene"):
        preview_frame(tmp_path / "v.mp4", [1.0], 0, 1.5)


def test_preview_frame_scene1_t0_selects_second_scene(tmp_path, tiny_video):
    """Scene 1 at t=0 must select the absolute time at the start of scene 1.

    scene_durations=[3.2, 4.1] means scene 0 is 0-3.2s, scene 1 is 3.2-7.3s.
    So scene_index=1, t=0 must map to abs_ts=3.2.
    """
    from animatica.pipeline import preview_frame

    video = tiny_video
    result = preview_frame(str(video), [0.9, 1.1], 1, 0.0)
    # Expected output: video_path.with_suffix(f".scene{scene_index}.t{t:.1f}.png")
    expected = video.with_name(f"{video.stem}.scene1.t0.0.png")
    assert result == expected


def test_preview_frame_scene0_t0_selects_first_scene(tiny_video):
    """Scene 0 at t=0 must select abs_ts=0 (start of scene 0)."""
    from animatica.pipeline import preview_frame

    video = tiny_video
    result = preview_frame(str(video), [0.9, 1.1], 0, 0.0)
    expected = video.with_name(f"{video.stem}.scene0.t0.0.png")
    assert result == expected


def test_fake_backend_satisfies_protocol():
    class Fake:
        name = "fake"
        supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]

        def capabilities(self) -> list[str]:
            return list(self.supported_capabilities)

        def render(self, sb, out_dir, opts):
            return RenderResult(
                video=Path(out_dir) / "v.mp4",
                durations=[1.0],
                warnings=[],
                stage_times={},
            )

    assert isinstance(Fake(), RenderBackend)


import json
import subprocess
from pathlib import Path

import pytest

from animatica.backends.base import RenderOptions
from animatica.backends.manim_backend import ManimBackend
from animatica.storyboard.models import Storyboard

TITLE_SB = Storyboard.model_validate(
    {
        "version": "1",
        "title": "Test",
        "scenes": [{"beats": [{"component": "title_card", "params": {"title": "Hello"}, "caption": "A test."}]}],
    }
)

BAD_LATEX_SB = Storyboard.model_validate(
    {
        "version": "1",
        "title": "Bad",
        "scenes": [{"beats": [{"component": "equation", "params": {"mode": "reveal", "latex": [r"\frac{a}{"]}, "caption": "x"}]}],
    }
)


def _ffprobe_duration(path: Path) -> float:
    """Container duration via PyAV (a Manim dependency): ffprobe is not available on every platform."""
    import av

    with av.open(str(path)) as c:
        return float(c.duration) / av.time_base


@pytest.mark.render
def test_manim_backend_render_one_scene(tmp_path):
    backend = ManimBackend()
    out = tmp_path / "out"
    result = backend.render(TITLE_SB, out, RenderOptions(quality="preview"))
    assert result.video.exists()
    assert result.durations == [3.0]
    assert result.stage_times
    dur = _ffprobe_duration(result.video)
    assert abs(dur - sum(result.durations)) <= 0.2, dur


@pytest.mark.render
def test_manim_backend_bad_latex_degrades_with_warning(tmp_path):
    backend = ManimBackend()
    out = tmp_path / "out"
    result = backend.render(BAD_LATEX_SB, out, RenderOptions(quality="preview"))
    assert result.video.exists()
    assert result.warnings, "expected at least one warning for bad latex"
    assert "equation" in result.warnings[0]



def test_failed_scene_error_includes_manim_output(tmp_path, monkeypatch):
    """A failing scene must say WHY (manim's stderr), not just 'non-zero exit status'."""
    import subprocess

    import pytest

    from animatica.backends.base import RenderOptions
    from animatica.backends.manim_backend import ManimBackend
    from animatica.storyboard.models import load_storyboard  # noqa: F401
    from animatica.ai.template import TemplateMatcher

    sb = TemplateMatcher().match("make a title card about Hello")

    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd, output="", stderr="LaTeX Error: File `standalone.cls' not found")

    monkeypatch.setattr("animatica.backends.manim_backend.subprocess.run", boom)
    with pytest.raises(RuntimeError) as exc:
        ManimBackend().render(sb, tmp_path, RenderOptions(quality="preview", captions=False))
    assert "standalone.cls" in str(exc.value)
    assert "scene 0" in str(exc.value)


@pytest.mark.render
def test_render_scenes_in_order_with_jobs_2(tmp_path, monkeypatch):
    """With jobs=2, two scenes render and concat in scene index order (subprocess.run faked)."""
    import subprocess as _subprocess
    import animatica.backends.manim_backend as mb
    from animatica.backends.base import RenderOptions
    from animatica.storyboard.models import Storyboard

    sb = Storyboard.model_validate(
        {
            "version": "1",
            "title": "Two",
            "scenes": [
                {"beats": [{"component": "title_card", "params": {"title": "One"}}]},
                {"beats": [{"component": "title_card", "params": {"title": "Two"}}]},
            ],
        }
    )

    import re
    import time

    rendered: list[int] = []
    concat_order: list[int] = []

    def fake_run(cmd, **kw):
        cmd = list(cmd)
        if "--media_dir" in cmd:  # the per-scene manim render
            idx = int(kw["env"]["ANIMATICA_SCENE_INDEX"])
            if idx == 0:
                time.sleep(0.3)  # scene 0 finishes last, so results arrive out of order
            media_dir = Path(cmd[cmd.index("--media_dir") + 1])
            media_dir.mkdir(parents=True, exist_ok=True)
            (media_dir / f"scene_{idx}.mp4").write_bytes(b"x")
            rendered.append(idx)
        else:  # ffmpeg concat: record clip order from the list file, then write dst
            listing = Path(cmd[cmd.index("-i") + 1]).read_text(encoding="utf-8")
            concat_order.extend(int(m) for m in re.findall(r"scene_(\d+)\.mp4", listing))
            Path(cmd[-1]).write_bytes(b"x")
        return _subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mb.subprocess, "run", fake_run)  # monkeypatch restores it on teardown
    result = mb.ManimBackend().render(sb, tmp_path, RenderOptions(quality="preview", jobs=2))

    assert result.video.exists()
    assert rendered == [1, 0], rendered  # out-of-order completion really happened
    assert concat_order == [0, 1], concat_order  # ...yet concat is in scene index order

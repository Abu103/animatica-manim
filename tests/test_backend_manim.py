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
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return float(out.stdout.strip())


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


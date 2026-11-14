import sys
import types

import pytest

from animatica.ai.base import extract_json
from animatica.components._latex import _tail_reason
from animatica.components.code_highlight import CodeHighlight
from animatica.backends.scheduler import concat_videos
from animatica.encode.transcode import transcode
from animatica.encode.probe import EncoderInfo


def test_code_caption_reads_params():
    component = CodeHighlight()
    assert component.fallback_text(component.Params(code="print(1)")) == "print(1)"


def test_extract_json_null_is_actionable():
    with pytest.raises(ValueError, match="provider output must be a string"):
        extract_json(None)


def test_babel_log_does_not_hide_unicode_error():
    reason, packages = _tail_reason("Package babel Info: english selected.\n! LaTeX Error: Unicode character अव not set up.\n")
    assert "babel-english" not in packages
    assert "Unicode" in reason


def test_missing_babel_english_still_reported():
    _, packages = _tail_reason("! Package babel Error: Unknown option 'english'.\n")
    assert "babel-english" in packages


def test_concat_uses_bundled_when_no_system_ffmpeg(monkeypatch, tmp_path):
    import animatica.backends.scheduler as scheduler
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", types.SimpleNamespace(get_ffmpeg_exe=lambda: "/bundle/ffmpeg"))
    calls = []
    monkeypatch.setattr(scheduler.subprocess, "run", lambda args, **kw: calls.append(args))
    concat_videos([tmp_path / "a.mp4", tmp_path / "b.mp4"], tmp_path / "out.mp4")
    assert calls[0][0] == "/bundle/ffmpeg"


def test_concat_explicit_ffmpeg_wins(monkeypatch, tmp_path):
    import animatica.backends.scheduler as scheduler
    calls = []
    monkeypatch.setattr(scheduler.subprocess, "run", lambda args, **kw: calls.append(args))
    concat_videos([tmp_path / "a.mp4"], tmp_path / "out.mp4", ffmpeg="custom-ffmpeg")
    assert calls[0][0] == "custom-ffmpeg"


def test_transcode_uses_default_resolver(monkeypatch, tmp_path):
    import animatica.encode.probe as probe
    monkeypatch.setattr(probe, "_default_ffmpeg", lambda: "/bundle/ffmpeg")
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return types.SimpleNamespace(returncode=1, stderr="failure", stdout="")
    src = tmp_path / "input.mp4"
    result = transcode(src, tmp_path / "out.mp4", EncoderInfo("libx264", "libx264", True, ""), run=run)
    assert calls[0][0] == "/bundle/ffmpeg"
    assert result.path == src and result.warning == "failure"


def test_array_search_indices_validated():
    from animatica.components.array_viz import ArrayViz
    ArrayViz.Params(title="Search", values=[1, 2, 3], steps=[{"low": 0, "high": 2, "mid": 1}])
    for step in ({"low": 999}, {"low": 2, "high": 1}, {"low": 1, "high": 2, "mid": 0}, {"mid": True}):
        with pytest.raises(ValueError):
            ArrayViz.Params(title="Search", values=[1, 2, 3], steps=[step])

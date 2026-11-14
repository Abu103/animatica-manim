"""T26d: ``animatica make --narrate`` -- synthesize, extend beats, build one track, mux.

Offline: Piper is replaced by a fake synthesizer that writes silent WAVs of a known
length, so every number asserted here is exact.
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path
from typing import ClassVar

import pytest

from animatica import narration, pipeline
from animatica.backends.base import RenderOptions, RenderResult
from animatica.narration import NarrationUnavailable


def _wav(path: Path, seconds: float, rate: int = 22050, sample: int = 0) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(int(seconds * rate) * sample.to_bytes(2, "little", signed=True))
    return path


def test_render_options_beat_floors_default_is_none():
    assert RenderOptions().beat_floors is None


def test_build_track_places_each_clip_at_its_beat_start(tmp_path):
    a = _wav(tmp_path / "a.wav", 1.0, sample=100)
    b = _wav(tmp_path / "b.wav", 0.5, sample=200)
    out = tmp_path / "track.wav"
    # beat 0 runs 2.0s (narration 1.0s), beat 1 runs 1.0s (narration 0.5s)
    narration.build_track([[a, b]], [[2.0, 1.0]], out)
    with wave.open(str(out), "rb") as w:
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
        assert abs(w.getnframes() / rate - 3.0) < 0.01  # the track is exactly the video length
    samples = [int.from_bytes(frames[i : i + 2], "little", signed=True) for i in range(0, len(frames), 2)]
    assert samples[int(0.5 * rate)] == 100  # inside clip a
    assert samples[int(1.5 * rate)] == 0  # padding after a, still inside beat 0
    assert samples[int(2.25 * rate)] == 200  # clip b starts at 2.0s
    assert samples[int(2.75 * rate)] == 0


def test_mux_narration_adds_an_audio_stream_and_keeps_the_video(tmp_path):
    from animatica._nativelibs import system_tool_env
    from animatica.encode.probe import _default_ffmpeg

    ffmpeg = _default_ffmpeg()
    video = tmp_path / "v.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2:r=10", "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True, env=system_tool_env(),
    )
    track = _wav(tmp_path / "t.wav", 2.0)
    out = narration.mux_narration(video, track, tmp_path / "narrated.mp4")
    import av

    with av.open(str(out)) as c:
        kinds = sorted(s.type for s in c.streams)
    assert kinds == ["audio", "video"]


def test_mux_failure_is_a_clear_error(tmp_path):
    with pytest.raises(NarrationUnavailable, match="mux"):
        narration.mux_narration(tmp_path / "missing.mp4", _wav(tmp_path / "t.wav", 1.0), tmp_path / "o.mp4")


def test_ensure_narration_rejects_unchecked_voice_before_any_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not fetch for an unchecked voice")

    monkeypatch.setattr(narration, "fetch_piper", boom)
    monkeypatch.setattr(narration, "fetch_voice_model", boom)
    with pytest.raises(NarrationUnavailable, match="allowlist"):
        narration.ensure_narration("en_GB-totally-unchecked")


def test_ensure_narration_uses_cached_files_without_fetching(monkeypatch, tmp_path):
    piper = tmp_path / "piper"
    piper.write_text("x")
    model = tmp_path / "v.onnx"
    model.write_text("x")
    monkeypatch.setattr(narration, "piper_binary_path", lambda: piper)
    monkeypatch.setattr(narration, "voice_model_file", lambda voice=narration.DEFAULT_VOICE: model)
    monkeypatch.setattr(narration.shutil, "which", lambda name: None)

    def boom(*a, **k):
        raise AssertionError("cached: no fetch")

    monkeypatch.setattr(narration, "fetch_piper", boom)
    monkeypatch.setattr(narration, "fetch_voice_model", boom)
    assert narration.ensure_narration() == (piper, model)


class _FakeManim:
    name = "manim"
    version = "fake"
    supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]
    seen_opts: ClassVar[list] = []

    def capabilities(self):
        return list(self.supported_capabilities)

    def render(self, sb, out_dir, opts):
        _FakeManim.seen_opts.append(opts)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "video.mp4").write_bytes(b"x")
        floors = opts.beat_floors or [[0.0] * len(s.beats) for s in sb.scenes]
        return RenderResult(video=Path(out_dir) / "video.mp4", durations=[sum(f) for f in floors], warnings=[], stage_times={"t": 1.0})


def _install_fakes(monkeypatch, tmp_path, narration_seconds):
    _FakeManim.seen_opts.clear()
    monkeypatch.setattr(pipeline, "default_backends", lambda: {"manim": _FakeManim()})
    monkeypatch.setattr(narration, "ensure_narration", lambda voice: (tmp_path / "piper", tmp_path / "v.onnx"))

    def fake_synth(text, out_path, voice=None, voice_model_path=None, **kw):
        out_path.parent.mkdir(parents=True, exist_ok=True)  # the real synthesize does the same
        return _wav(out_path, narration_seconds)

    monkeypatch.setattr(narration, "synthesize", fake_synth)
    muxed = {}

    def fake_mux(video, track, out, ffmpeg=None):
        muxed.update(video=video, track=track, out=out)
        Path(out).write_bytes(b"narrated")
        return Path(out)

    monkeypatch.setattr(narration, "mux_narration", fake_mux)
    return muxed


def test_make_video_narrate_feeds_floors_muxes_and_records_voice(monkeypatch, tmp_path):
    muxed = _install_fakes(monkeypatch, tmp_path, narration_seconds=9.0)
    out = tmp_path / "out"
    result = pipeline.make_video("make a title card about Hello", out_dir=out, preview=True, narrate=True, frame_lint=False)
    opts = _FakeManim.seen_opts[0]
    assert opts.beat_floors and opts.beat_floors[0][0] == pytest.approx(9.0, abs=0.01)
    assert result.video == out / "video_narrated.mp4" and result.video.read_bytes() == b"narrated"
    assert muxed["track"].exists()
    import json

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["narration"]["voice"] == narration.DEFAULT_VOICE
    assert "public domain" in report["narration"]["license"]
    # captions follow the extended beat, not the shorter visual duration
    vtt = (out / "captions.vtt").read_text(encoding="utf-8")
    assert "00:00:09.000" in vtt


def test_make_video_without_narrate_is_unchanged(monkeypatch, tmp_path):
    _install_fakes(monkeypatch, tmp_path, narration_seconds=9.0)
    out = tmp_path / "out"
    result = pipeline.make_video("make a title card about Hello", out_dir=out, preview=True, frame_lint=False)
    assert _FakeManim.seen_opts[0].beat_floors is None
    assert result.video.name == "video.mp4"
    import json

    assert "narration" not in json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert "00:00:09.000" not in (out / "captions.vtt").read_text(encoding="utf-8")


def test_narrate_with_a_non_manim_backend_fails_before_synthesis(monkeypatch, tmp_path):
    class Other(_FakeManim):
        name = "other"

    monkeypatch.setattr(pipeline, "default_backends", lambda: {"other": Other()})

    def boom(*a, **k):
        raise AssertionError("must not synthesize")

    monkeypatch.setattr(narration, "ensure_narration", boom)
    with pytest.raises(ValueError, match="--narrate.*manim"):
        pipeline.make_video("make a title card about Hello", out_dir=tmp_path, backend="other", narrate=True)


def test_missing_narration_fails_closed_with_the_doctor_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "default_backends", lambda: {"manim": _FakeManim()})

    def unavailable(voice):
        raise NarrationUnavailable("piper download failed: offline")

    monkeypatch.setattr(narration, "ensure_narration", unavailable)
    with pytest.raises(NarrationUnavailable, match="offline"):
        pipeline.make_video("make a title card about Hello", out_dir=tmp_path, narrate=True)
    assert not (tmp_path / "video.mp4").exists()  # never silently rendered without narration


def test_cli_narrate_failure_exits_nonzero_without_traceback(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from animatica.cli import app

    def unavailable(voice):
        raise NarrationUnavailable("the voice model is not installed; run `animatica doctor --fix`")

    monkeypatch.setattr(narration, "ensure_narration", unavailable)
    r = CliRunner().invoke(app, ["make", "make a title card about hello", "--narrate", "-o", str(tmp_path)])
    assert r.exit_code == 1 and "Traceback" not in r.output and "doctor --fix" in r.output


def test_cli_rejects_unknown_voice(tmp_path):
    from typer.testing import CliRunner

    from animatica.cli import app

    r = CliRunner().invoke(app, ["make", "make a title card about hello", "--narrate", "--voice", "nope", "-o", str(tmp_path)])
    assert r.exit_code == 1 and "allowlist" in r.output


def test_clock_budget_grows_by_the_scene_narration_hold():
    """The hold lands before the closing fade-out, so a narrated beat never ends on a blank frame."""
    from types import SimpleNamespace

    from animatica.components._draw import Clock

    assert Clock(SimpleNamespace(narration_hold=2.5), 3.0, fps=15).total == 5.5
    assert Clock(SimpleNamespace(), 3.0, fps=15).total == 3.0  # no --narrate: unchanged

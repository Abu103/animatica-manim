"""C2: the bundled cairo/pango directory must not reach ffmpeg.

`.animatica-env` and `_nativelibs.ensure()` put the runtime's `native/lib` on
LD_LIBRARY_PATH so the `manim` child can find cairo and pango. A system ffmpeg
inherits the same variable and then loads the bundle's glib instead of its own
(`symbol lookup error: ... g_task_set_static_name`, exit 127), so a render with
two scenes died at the concat step. ffmpeg needs none of the bundle, so every
ffmpeg call runs with the bundle directory removed.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from animatica import _nativelibs
from animatica.backends.scheduler import concat_videos
from animatica.encode.probe import EncoderInfo, probe_encoders
from animatica.encode.transcode import transcode

BUNDLE = "/rt/native/lib"
KEEP = "/usr/lib/keep"
SEP = os.pathsep  # ":" on POSIX, ";" on Windows, where this variable means nothing but must not crash


def _entries(env):
    """LD_LIBRARY_PATH entries, normalised so "/a/b/" and "\\a\\b" compare equal on any OS."""
    return [os.path.normpath(e) for e in env.get("LD_LIBRARY_PATH", "").split(SEP) if e]


def _has_bundle(env):
    return os.path.normpath(BUNDLE) in _entries(env)


class _CP:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _bundle_env(monkeypatch, ld=None):
    monkeypatch.setenv(_nativelibs.NATIVE_DIR_ENV, BUNDLE)
    monkeypatch.setenv("LD_LIBRARY_PATH", BUNDLE + SEP + KEEP if ld is None else ld)


def _ld(env):
    return env.get("LD_LIBRARY_PATH", "")


def test_system_tool_env_drops_only_the_bundle_dir(monkeypatch):
    _bundle_env(monkeypatch)
    env = _nativelibs.system_tool_env()
    assert _ld(env) == KEEP


def test_system_tool_env_removes_the_variable_when_nothing_else_is_left(monkeypatch):
    _bundle_env(monkeypatch, ld=BUNDLE)
    assert "LD_LIBRARY_PATH" not in _nativelibs.system_tool_env()


def test_system_tool_env_leaves_the_process_environment_alone(monkeypatch):
    _bundle_env(monkeypatch)
    _nativelibs.system_tool_env()
    assert os.environ["LD_LIBRARY_PATH"] == BUNDLE + SEP + KEEP


def test_system_tool_env_keeps_unrelated_entries_and_other_variables(monkeypatch):
    monkeypatch.delenv(_nativelibs.NATIVE_DIR_ENV, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/a" + SEP + "/b")
    monkeypatch.setenv("ANIMATICA_PROBE", "1")
    env = _nativelibs.system_tool_env()
    assert _ld(env) == "/a" + SEP + "/b"
    assert env["ANIMATICA_PROBE"] == "1"


def test_system_tool_env_without_the_variable_adds_nothing(monkeypatch):
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    monkeypatch.delenv(_nativelibs.NATIVE_DIR_ENV, raising=False)
    assert "LD_LIBRARY_PATH" not in _nativelibs.system_tool_env()


def test_system_tool_env_matches_a_trailing_slash(monkeypatch):
    monkeypatch.setenv(_nativelibs.NATIVE_DIR_ENV, BUNDLE)
    monkeypatch.setenv("LD_LIBRARY_PATH", BUNDLE + "/" + SEP + KEEP)
    assert _ld(_nativelibs.system_tool_env()) == KEEP


def test_concat_runs_ffmpeg_without_the_bundle(tmp_path, monkeypatch):
    _bundle_env(monkeypatch)
    seen = {}

    def fake_run(args, **kwargs):
        seen["env"] = kwargs.get("env")
        Path(args[-1]).touch()

    monkeypatch.setattr("animatica.backends.scheduler.subprocess.run", fake_run)
    concat_videos([tmp_path / "a.mp4", tmp_path / "b.mp4"], tmp_path / "o.mp4", ffmpeg="ffmpeg")
    assert seen["env"] is not None, "concat must pass an explicit env"
    assert not _has_bundle(seen["env"])
    assert os.path.normpath(KEEP) in _entries(seen["env"])


def test_transcode_runs_ffmpeg_without_the_bundle(tmp_path, monkeypatch):
    _bundle_env(monkeypatch)
    src, dst = tmp_path / "in.mp4", tmp_path / "out.mp4"
    src.write_bytes(b"x")
    seen = {}

    def run(args, **kwargs):
        seen["env"] = kwargs.get("env")
        dst.write_bytes(b"out")
        return _CP()

    transcode(src, dst, EncoderInfo("libx264", "libx264", True, ""), ffmpeg="ffmpeg", run=run)
    assert seen["env"] is not None
    assert not _has_bundle(seen["env"])


def test_probe_runs_every_ffmpeg_call_without_the_bundle(monkeypatch):
    _bundle_env(monkeypatch)
    envs = []

    def run(args, **kwargs):
        if args[0] == "ffmpeg":
            envs.append(kwargs.get("env"))
        a = list(args)
        if a[1:] == ["-version"]:
            return _CP(0, "ffmpeg version 6.0")
        if a[1:] == ["-encoders"]:
            return _CP(0, " libx264 ")
        return _CP(0, "", "")

    probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None)
    assert len(envs) >= 2, "expected -version, -encoders and a test encode"
    for env in envs:
        assert env is not None
        assert not _has_bundle(env)


def test_real_subprocess_sees_no_bundle_dir(tmp_path, monkeypatch):
    """End to end through subprocess: the child process environment is what ffmpeg would get."""
    import sys

    _bundle_env(monkeypatch)
    out = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ.get('LD_LIBRARY_PATH', ''))"],
        env=_nativelibs.system_tool_env(),
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == KEEP

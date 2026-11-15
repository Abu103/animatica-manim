"""T26c: lazy-fetch of the Piper binary and the default voice model.

docs/superpowers/specs/2026-11-14-narration-design.md section 5: lazy-fetch,
never bundled; same fail-closed, pinned-sha256 posture as the Windows TeX
bundle (``tex_bundle.py``). Every download is faked here -- no real network
call is made in this test file, and none of Piper's real bytes are needed to
prove the hash-check logic.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from animatica import narration


def _fake_download(content: bytes):
    def _dl(url, dest, timeout=600):
        dest.write_bytes(content)
        return dest

    return _dl


def test_fetch_piper_uses_the_cached_binary_without_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    cached = tmp_path / "piper" / "piper"
    cached.parent.mkdir(parents=True)
    cached.write_text("already here", encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("should not download when already cached")

    assert narration.fetch_piper(download_fn=_boom, platform="linux") == cached


def test_fetch_piper_rejects_a_hash_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    with pytest.raises(narration.NarrationUnavailable, match="hash mismatch"):
        narration.fetch_piper(download_fn=_fake_download(b"not the real piper tarball"), platform="linux")
    assert not narration.piper_binary_path().is_file()


class _Proc:
    def __init__(self, rc=0, err=""):
        self.returncode, self.stderr = rc, err


@pytest.mark.parametrize("plat", ["win32", "darwin"])
def test_fetch_piper_off_linux_pip_installs_instead_of_downloading_the_linux_binary(tmp_path, monkeypatch, plat):
    # The WinError 193 bug: the Linux ELF tarball must never be fetched here.
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    monkeypatch.setattr(narration.sysconfig, "get_path", lambda name: str(scripts))
    monkeypatch.setattr(narration.sys, "executable", str(scripts / "python.exe"))
    calls = []

    def _run(cmd, **kw):
        calls.append(cmd)
        (scripts / "piper.exe").write_text("exe", encoding="utf-8")  # what pip leaves behind
        return _Proc()

    def _boom(*a, **k):
        raise AssertionError("must not download the Linux tarball off Linux")

    got = narration.fetch_piper(download_fn=_boom, platform=plat, run=_run)
    assert got == scripts / "piper.exe"
    assert calls[0][1:5] == ["-m", "pip", "install", "piper-tts"]


def test_fetch_piper_off_linux_reuses_an_existing_pip_install(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "piper.exe").write_text("exe", encoding="utf-8")
    monkeypatch.setattr(narration.sysconfig, "get_path", lambda name: str(scripts))

    def _boom(*a, **k):
        raise AssertionError("already installed: no pip run")

    assert narration.fetch_piper(platform="win32", run=_boom) == scripts / "piper.exe"


def test_fetch_piper_off_linux_reports_a_failed_pip_install(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    monkeypatch.setattr(narration.sysconfig, "get_path", lambda name: str(tmp_path / "empty"))
    monkeypatch.setattr(narration.sys, "executable", str(tmp_path / "py"))
    monkeypatch.setattr(narration.shutil, "which", lambda name: None)
    with pytest.raises(narration.NarrationUnavailable, match="pip install piper-tts"):
        narration.fetch_piper(platform="win32", run=lambda cmd, **kw: _Proc(1, "No matching distribution"))


def test_find_piper_prefers_path_then_cache_then_pip(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    monkeypatch.setattr(narration.sysconfig, "get_path", lambda name: str(tmp_path / "none"))
    monkeypatch.setattr(narration.sys, "executable", str(tmp_path / "none" / "py"))
    assert narration.find_piper(which=lambda n: None) is None
    assert narration.find_piper(which=lambda n: "/usr/bin/piper") == Path("/usr/bin/piper")


def test_find_piper_ignores_a_stale_linux_binary_in_the_cache_off_linux(tmp_path, monkeypatch):
    # The real-world WinError 193 repro: an older `doctor --fix` left the Linux ELF at piper/piper.
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    stale = tmp_path / "piper" / "piper"
    stale.parent.mkdir(parents=True)
    stale.write_text("ELF", encoding="utf-8")
    monkeypatch.setattr(narration.sysconfig, "get_path", lambda name: str(tmp_path / "none"))
    monkeypatch.setattr(narration.sys, "executable", str(tmp_path / "none" / "py"))
    monkeypatch.setattr(narration, "_is_linux", lambda: False)
    assert narration.find_piper(which=lambda n: None) is None
    monkeypatch.setattr(narration, "_is_linux", lambda: True)
    assert narration.find_piper(which=lambda n: None) == stale


def test_fetch_piper_still_uses_the_cached_binary_on_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    cached = tmp_path / "piper" / "piper"
    cached.parent.mkdir(parents=True)
    cached.write_text("already here", encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("cached binary should short-circuit")

    assert narration.fetch_piper(platform="linux", download_fn=_boom) == cached


def test_fetch_piper_wraps_a_download_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)

    def _fails(url, dest, timeout=600):
        raise OSError("network unreachable")

    with pytest.raises(narration.NarrationUnavailable, match="download failed"):
        narration.fetch_piper(download_fn=_fails, platform="linux")


def test_fetch_voice_model_rejects_an_unchecked_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    with pytest.raises(narration.NarrationUnavailable, match="allowlist"):
        narration.fetch_voice_model(voice="some-unvetted-voice")


def test_fetch_voice_model_verifies_the_real_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    content = b"a fake onnx file standing in for the real voice model"
    digest = hashlib.sha256(content).hexdigest()
    monkeypatch.setitem(narration.VOICE_MODEL_SHA256, narration.DEFAULT_VOICE, digest)

    path = narration.fetch_voice_model(download_fn=_fake_download(content))
    assert path == narration.voice_model_file()
    assert path.read_bytes() == content
    assert (path.parent / f"{narration.DEFAULT_VOICE}.onnx.json").is_file()


def test_fetch_voice_model_rejects_a_hash_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    monkeypatch.setitem(narration.VOICE_MODEL_SHA256, narration.DEFAULT_VOICE, "0" * 64)
    with pytest.raises(narration.NarrationUnavailable, match="hash mismatch"):
        narration.fetch_voice_model(download_fn=_fake_download(b"wrong bytes"))
    assert not narration.voice_model_file().is_file()


def test_fetch_voice_model_returns_the_cached_file_when_hash_already_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    content = b"cached voice model bytes"
    digest = hashlib.sha256(content).hexdigest()
    monkeypatch.setitem(narration.VOICE_MODEL_SHA256, narration.DEFAULT_VOICE, digest)
    narration.voice_model_file().write_bytes(content)

    def _boom(*a, **k):
        raise AssertionError("should not download when the cached file already matches")

    assert narration.fetch_voice_model(download_fn=_boom) == narration.voice_model_file()

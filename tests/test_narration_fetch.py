"""T26c: lazy-fetch of the Piper binary and the default voice model.

docs/superpowers/specs/2026-11-14-narration-design.md section 5: lazy-fetch,
never bundled; same fail-closed, pinned-sha256 posture as the Windows TeX
bundle (``tex_bundle.py``). Every download is faked here -- no real network
call is made in this test file, and none of Piper's real bytes are needed to
prove the hash-check logic.
"""
from __future__ import annotations

import hashlib

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

    assert narration.fetch_piper(download_fn=_boom) == cached


def test_fetch_piper_rejects_a_hash_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)
    with pytest.raises(narration.NarrationUnavailable, match="hash mismatch"):
        narration.fetch_piper(download_fn=_fake_download(b"not the real piper tarball"))
    assert not narration.piper_binary_path().is_file()


def test_fetch_piper_wraps_a_download_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(narration, "narration_dir", lambda: tmp_path)

    def _fails(url, dest, timeout=600):
        raise OSError("network unreachable")

    with pytest.raises(narration.NarrationUnavailable, match="download failed"):
        narration.fetch_piper(download_fn=_fails)


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

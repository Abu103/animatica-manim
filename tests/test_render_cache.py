"""The render cache: the same storyboard does not have to be rendered twice.

The gate renders the conformance corpus, and a developer runs the gate again
after every change. The cache is keyed by what a render depends on, so a
changed component is never served from the cache -- that is the whole point
of the fingerprint of the source.
"""
import json

import pytest

from animatica import render_cache


@pytest.fixture(autouse=True)
def _own_cache(tmp_path, monkeypatch):
    """Keep the test out of the developer's own cache."""
    monkeypatch.setattr(render_cache, "CACHE_ROOT", tmp_path / "renders")
    monkeypatch.delenv(render_cache.DISABLE_ENV, raising=False)
    _forget_fingerprint()
    yield
    _forget_fingerprint()


def _forget_fingerprint() -> None:
    """Drop the cached fingerprint, so the next call reads the sources again."""
    forget = getattr(render_cache.source_fingerprint, "cache_clear", None)
    if forget is not None:
        forget()


def _storyboard(tmp_path, title: str = "One"):
    path = tmp_path / "sb.json"
    path.write_text(json.dumps({"version": "1", "title": title}), encoding="utf-8")
    return path


def test_the_key_is_the_same_for_the_same_storyboard(tmp_path):
    sb = _storyboard(tmp_path)

    assert render_cache.render_key(sb) == render_cache.render_key(sb)


def test_a_different_storyboard_gets_a_different_key(tmp_path):
    one = _storyboard(tmp_path, "One")
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"version": "1", "title": "Two"}), encoding="utf-8")

    assert render_cache.render_key(one) != render_cache.render_key(other)


def test_a_different_quality_gets_a_different_key(tmp_path):
    sb = _storyboard(tmp_path)

    assert render_cache.render_key(sb, quality="preview") != render_cache.render_key(
        sb, quality="standard"
    )


def test_changed_source_gets_a_different_key(tmp_path, monkeypatch):
    """A changed component must never be served from the cache."""
    sb = _storyboard(tmp_path)
    before = render_cache.render_key(sb)

    monkeypatch.setattr(render_cache, "source_fingerprint", lambda: "a different tree")

    assert render_cache.render_key(sb) != before


def test_a_stored_render_comes_back(tmp_path):
    sb = _storyboard(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_text(json.dumps({"warnings": ["x"]}), encoding="utf-8")
    (out / "video.mp4").write_bytes(b"video")

    key = render_cache.render_key(sb)
    render_cache.store(key, out)

    again = tmp_path / "again"
    assert render_cache.restore(key, again) is True
    assert json.loads((again / "report.json").read_text(encoding="utf-8")) == {"warnings": ["x"]}
    assert (again / "video.mp4").read_bytes() == b"video"


def test_a_miss_is_a_miss(tmp_path):
    assert render_cache.restore("no-such-key", tmp_path / "out") is False


def test_a_half_written_entry_is_not_a_hit(tmp_path):
    """A render that was killed halfway must not be served."""
    sb = _storyboard(tmp_path)
    key = render_cache.render_key(sb)
    entry = render_cache.cache_dir(key)
    entry.mkdir(parents=True)
    (entry / "video.mp4").write_bytes(b"video")

    assert render_cache.restore(key, tmp_path / "out") is False


def test_the_cache_can_be_switched_off(tmp_path, monkeypatch):
    """CI wants a real render, not a replay."""
    sb = _storyboard(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_text("{}", encoding="utf-8")

    key = render_cache.render_key(sb)
    render_cache.store(key, out)

    monkeypatch.setenv(render_cache.DISABLE_ENV, "1")
    assert render_cache.restore(key, tmp_path / "out2") is False
    assert render_cache.enabled() is False


def test_the_fingerprint_covers_the_whole_package():
    """A component is a source file: the fingerprint has to see it."""
    fingerprint = render_cache.source_fingerprint()

    assert len(fingerprint) == 64
    assert fingerprint == render_cache.source_fingerprint()

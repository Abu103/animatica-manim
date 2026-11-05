import pytest

from animatica.pipeline import cache_variant, make_video, resolve_backend
from types import SimpleNamespace


def test_cache_variant_differs_by_model(registry):
    a = SimpleNamespace(name="nim", model="m1"); b = SimpleNamespace(name="nim", model="m2")
    assert cache_variant(a, False, registry) != cache_variant(b, False, registry)


def test_cache_variant_differs_by_mode(registry):
    p = SimpleNamespace(name="nim", model="m1")
    assert cache_variant(p, True, registry) != cache_variant(p, False, registry)


def test_make_end_to_end(tmp_path):
    result = make_video("make a title card about Hello", out_dir=tmp_path, preview=True)
    assert result.video.exists()
    assert result.storyboard.exists()
    assert result.captions.exists()
    assert result.report.exists()
    assert result.warnings == []



@pytest.mark.render
def test_failed_transcode_returns_the_real_video_and_keeps_the_warning(tmp_path, monkeypatch):
    """A failed non-default transcode must not leave `video` pointing at a file that was never made."""
    from animatica import pipeline
    from animatica.encode.probe import EncoderInfo, TranscodeResult

    enc = EncoderInfo("libx264", "libx264", True, "")
    monkeypatch.setattr(pipeline, "probe_encoders", lambda: [enc])
    monkeypatch.setattr(pipeline, "pick_encoder", lambda name, infos: enc)

    def failing_transcode(src, dst, e, **kw):
        return TranscodeResult(path=src, encoder=e, warning="boom")

    monkeypatch.setattr(pipeline, "transcode", failing_transcode)
    result = make_video("make a title card about Hello", out_dir=tmp_path, preview=True, encoder="libx264")
    assert result.video.exists()
    assert result.video.name != "video_transcoded.mp4"
    assert any("transcode: boom" in w for w in result.warnings)


def test_resolve_backend_unknown_lists_available():
    with pytest.raises(ValueError, match=r"unknown backend 'nope'; available: .*manim"):
        resolve_backend("nope")


def test_report_records_backend(tmp_path):
    from animatica.report import write_report
    import json
    write_report(tmp_path / "r.json", {"a": 1.0}, [], backend={"name": "manim", "version": "0.22.1"})
    assert json.loads((tmp_path / "r.json").read_text())["backend"]["name"] == "manim"


def test_make_video_uses_injected_backend_not_manim(monkeypatch, tmp_path):
    """An injected fake backend (via monkeypatch on default_backends) is called instead of ManimBackend."""
    import pathlib
    import animatica.pipeline as pipeline
    from animatica.backends.base import RenderResult

    class FakeBackend:
        name = "fake"
        version = "9.9"

        def render(self, sb, out_dir, opts):
            out_dir = pathlib.Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "video.mp4").write_bytes(b"x")
            return RenderResult(
                video=out_dir / "video.mp4",
                durations=[1.0],
                warnings=[],
                stage_times={"total": 1.0},
            )

    def fake_default_backends():
        return {"fake": FakeBackend()}
    monkeypatch.setattr("animatica.pipeline.default_backends", fake_default_backends)
    monkeypatch.setattr(pipeline, "ManimBackend", lambda: (_ for _ in ()).throw(AssertionError("ManimBackend must not be instantiated")))

    result = pipeline.make_video("make a title card about Hello", out_dir=tmp_path, preview=True, backend="fake")
    assert result.video.exists()


def test_unknown_backend_fails_before_provider_call_or_any_file(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("animatica.pipeline.get_provider", lambda name, cfg: calls.append(name))
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="available:"):
        make_video("explain quicksort", out_dir=out, provider="nim", backend="nope")
    assert calls == []  # no LLM spend on a typo'd backend
    assert not out.exists()  # nothing written

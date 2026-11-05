import pytest

from animatica.pipeline import cache_variant, make_video
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

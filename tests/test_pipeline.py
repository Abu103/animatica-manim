import pytest
from pathlib import Path
from typing import ClassVar

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
        supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]

        def capabilities(self) -> list[str]:
            return list(self.supported_capabilities)

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


def test_guidance_notes_appear_in_pipeline_warnings(tmp_path):
    """A storyboard whose caption describes production mechanics should
    surface a guidance note in make_video warnings."""
    import json as _json

    # Hand-written storyboard with a "title card introducing" caption
    sb_path = tmp_path / "storyboard.json"
    sb_path.write_text(
        _json.dumps({
            "version": "1",
            "title": "Guidance Test",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "title_card",
                            "params": {"title": "Guidance Test"},
                            "caption": "A title card introducing the guidance test topic.",
                        }
                    ]
                }
            ],
        }),
        encoding="utf-8",
    )

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "out",
        preview=True,
    )
    assert result.video.exists()
    guidance_warnings = [w for w in result.warnings if "guidance" in w.lower() or "production mechanics" in w.lower()]
    assert len(guidance_warnings) >= 1, f"expected guidance note, got warnings: {result.warnings}"


# ---------------------------------------------------------------------------
# End-to-end graph comparison regression test
# ---------------------------------------------------------------------------

_CYAN = (56, 189, 248)   # dark-blue theme accent: original curve (e^x)
_WHITE = (255, 255, 255)  # dark-blue theme text: approximation curve


def _curve_colors_present(video_path: str, t: float) -> dict[str, object]:
    """Extract a frame at `t` and report whether cyan and white curve pixels
    appear in the plot area (above the caption band)."""
    import av
    import numpy as np
    from PIL import Image

    container = av.open(video_path)
    try:
        video_stream = next(s for s in container.streams if s.type == "video")
        target = None
        for frame in container.decode(video_stream):
            ts = float(frame.time) if frame.time is not None else 0
            if ts >= t:
                target = frame
                break
        if target is None:
            return {"cyan": False, "white": False, "error": "no frame"}
        img = Image.fromarray(target.to_ndarray(format="rgb24")).convert("RGB")
    finally:
        container.close()

    arr = np.array(img)
    h, w, _ = arr.shape
    # Plot area: above the bottom caption band (last ~8% of height)
    plot = arr[: int(h * 0.85), :, :]

    def color_present(rgb, tol=40):
        mask = np.all(np.abs(plot.astype(int) - np.array(rgb)) <= tol, axis=2)
        return bool(mask.sum() > 50)  # at least 50 pixels of that color

    return {"cyan": color_present(_CYAN), "white": color_present(_WHITE)}


@pytest.mark.render
def test_taylor_graph_end_to_end_both_curves_visible(tmp_path):
    """End-to-end: rendering a Taylor storyboard produces a graph frame
    where both the original function and the approximation curves are
    visible and distinguishable.

    Uses a hand-written fixture stored inline (not an untracked acceptance
    artifact) so the test works on a clean checkout.
    """
    import json as _json

    sb_path = tmp_path / "taylor_fixture.json"
    sb_path.write_text(
        _json.dumps({
            "version": "1",
            "title": "Taylor Series",
            "theme": {"palette": "dark-blue", "font": "default"},
            "scenes": [{
                "beats": [
                    {"component": "title_card", "params": {"title": "Taylor Series",
                        "subtitle": "Approximating functions with polynomials"},
                        "caption": "Taylor series approximate smooth functions with polynomials."},
                    {"component": "equation", "params": {"mode": "reveal",
                        "latex": ["f(x) = \\sum_{n=0}^{\\infty} \\frac{f^{(n)}(a)}{n!}(x-a)^n"]},
                        "caption": "The series adds derivative-based terms to match a function at a point."},
                    {"component": "graph", "params": {
                        "fn": "exp(x)", "approx_fn": "1 + x + x**2/2 + x**3/6",
                        "x_range": [-2, 2], "y_range": [0, 8],
                        "label": "e^x", "approx_label": "3rd-degree Taylor polynomial"},
                        "caption": "A low-degree polynomial follows e^x near zero but drifts away at the edges."},
                ]
            }],
        }),
        encoding="utf-8",
    )

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "taylor_e2e",
        preview=True,
    )
    assert result.video.exists()

    # Graph beat is the last beat in the single scene; sample late in the
    # video after both Create animations should have finished.
    info = _curve_colors_present(str(result.video), t=8.0)
    assert not info.get("error"), f"frame extraction failed: {info.get('error')}"
    assert info["cyan"], "original function curve (cyan/e^x) not visible in graph frame"
    assert info["white"], "approximation curve (white/Taylor polynomial) not visible in graph frame"


@pytest.mark.render
def test_graph_end_to_end_legend_and_clipping_warning(tmp_path):
    """End-to-end: a graph with approx_fn produces a legend, and a curve
    clipped by the y-range produces a warning (it does not silently vanish)."""
    import json as _json

    sb_path = tmp_path / "graph_fixture.json"
    sb_path.write_text(
        _json.dumps({
            "version": "1",
            "title": "Graph Fixture",
            "theme": {"palette": "dark-blue", "font": "default"},
            "scenes": [{
                "beats": [{
                    "component": "graph", "params": {
                        "fn": "exp(x)", "approx_fn": "1 + x",
                        "x_range": [-2, 2], "y_range": [0, 2],
                        "label": "e^x", "approx_label": "linear approx",
                        "caption": "e^x is clipped at y=2; the linear approximation stays in range.",
                    }
                }]
            }],
        }),
        encoding="utf-8",
    )

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "graph_e2e",
        preview=True,
    )
    assert result.video.exists()

    # The graph scene renders scene index 0; extract warnings from the report.
    report_path = result.report
    assert report_path.exists()
    report = _json.loads(report_path.read_text(encoding="utf-8"))
    warnings = report.get("warnings", [])

    # exp(x) at x=2 gives e^2 ≈ 7.39, which exceeds y_range [0, 2], so it
    # should be flagged as clipped.
    clipped_warnings = [w for w in warnings if "clipped" in w.lower()]
    assert len(clipped_warnings) >= 1, f"expected clipping warning, got warnings: {warnings}"

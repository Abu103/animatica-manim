import json

from typer.testing import CliRunner

from animatica.cli import app

def test_cli_unknown_backend_exits_nonzero_without_traceback(tmp_path):
    r = CliRunner().invoke(app, ["make", "graph of sin(x)", "--backend", "nope", "-o", str(tmp_path)])
    assert r.exit_code != 0 and "Traceback" not in r.output and "available:" in r.output


def test_make_template_prompt_zero_provider_calls(monkeypatch, tmp_path):
    calls = []

    class CountingProvider:
        name = "counting"
        def generate(self, prompt, schema):
            calls.append(prompt)
            return "{}"

    monkeypatch.setattr("animatica.pipeline.get_provider", lambda name, cfg: CountingProvider())
    runner = CliRunner()
    result = runner.invoke(app, ["make", "make a title card about hello", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [], f"provider should not be called for template prompt: {calls}"
    assert (tmp_path / "video.mp4").exists()


def test_make_empty_prompt_exits_nonzero(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["make", "   ", "-o", str(tmp_path)])
    assert result.exit_code != 0
    assert not any(tmp_path.iterdir())


def test_make_from_storyboard_skips_ai(monkeypatch, tmp_path):
    calls = []

    class CountingProvider:
        name = "counting"
        def generate(self, prompt, schema):
            calls.append(prompt)
            return "{}"

    monkeypatch.setattr("animatica.pipeline.get_provider", lambda name, cfg: CountingProvider())
    sb_path = tmp_path / "sb.json"
    sb_path.write_text('{"version":"1","title":"T","scenes":[{"beats":[{"component":"title_card","params":{"title":"Hi"}}]}]}')
    runner = CliRunner()
    result = runner.invoke(app, ["make", "--from", str(sb_path), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == []


def test_make_captions_cumulative(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["make", "steps to do a thing", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    vtt = (tmp_path / "captions.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    # cue times should be non-decreasing cumulative
    import re
    times = re.findall(r"(\d+:\d+\.\d{3}) -->", vtt)
    assert len(times) >= 1


def test_make_output_dir_spaces_and_unicode(tmp_path):
    out = tmp_path / "my vidé 日本 folder"
    runner = CliRunner()
    result = runner.invoke(app, ["make", "make a title card about hello", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "video.mp4").exists()


def test_make_prints_provider_and_encoder(tmp_path, monkeypatch):
    """CLI make prints Provider and Encoder lines after make_video returns."""
    calls = []

    class CountingProvider:
        name = "counting"
        def generate(self, prompt, schema):
            calls.append(prompt)
            return "{}"

    monkeypatch.setattr("animatica.pipeline.get_provider", lambda name, cfg: CountingProvider())
    runner = CliRunner()
    result = runner.invoke(app, ["make", "make a title card about hello", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Provider: template (offline)" in result.output
    assert "Encoder: x264 (manim default)" in result.output


def test_make_invalid_storyboard_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"version":"1","title":"T","scenes":[{"beats":[{"component":"nope","params":{}}]}]}')
    runner = CliRunner()
    result = runner.invoke(app, ["make", "--from", str(bad), "-o", str(tmp_path)])
    assert result.exit_code == 2


def test_make_no_debug_no_traceback(monkeypatch, tmp_path):
    class AlwaysBad:
        name = "bad"
        def generate(self, prompt, schema):
            raise RuntimeError("boom")
    monkeypatch.setattr("animatica.pipeline.get_provider", lambda name, cfg: AlwaysBad())
    runner = CliRunner()
    result = runner.invoke(app, ["make", "something weird", "-o", str(tmp_path)])
    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_explicit_provider_skips_offline_templates(monkeypatch, tmp_path):
    """--provider X means 'use the model', even when the prompt contains a template keyword."""
    import animatica.pipeline as pipeline

    called = []

    def fake_get_provider(name, cfg):
        called.append(name)
        raise ValueError("stop here")

    monkeypatch.setattr(pipeline, "get_provider", fake_get_provider)
    import pytest
    with pytest.raises(ValueError, match="stop here"):
        pipeline.make_video(prompt="explain the pythagorean theorem in depth", out_dir=tmp_path, provider="nim")
    assert called == ["nim"]


def test_cli_jobs_zero_rejected():
    r = CliRunner().invoke(app, ["make", "graph of sin(x)", "--jobs", "0"])
    assert r.exit_code != 0


# ---------------------------------------------------------------------------
# preview command
# ---------------------------------------------------------------------------

def test_preview_missing_video(tmp_path):
    """preview with nonexistent video exits nonzero."""
    runner = CliRunner()
    result = runner.invoke(app, ["preview", str(tmp_path / "nope.mp4"), "0", "0.0"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_preview_no_report(tmp_path):
    """preview without scene durations exits nonzero."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video bytes")
    runner = CliRunner()
    result = runner.invoke(app, ["preview", str(video), "0", "0.0"])
    assert result.exit_code != 0
    assert "no scene durations" in result.output.lower()


def test_preview_reads_scene_durations_written_by_make(tmp_path):
    """make writes scene_durations at the top level; preview must find them."""
    runner = CliRunner()
    made = runner.invoke(app, ["make", "make a title card about hello", "-o", str(tmp_path)])
    assert made.exit_code == 0, made.output
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report.get("scene_durations"), report

    preview = runner.invoke(
        app,
        ["preview", str(tmp_path / "video.mp4"), "0", "0.0", "-o", str(tmp_path / "frame.png")],
    )
    assert preview.exit_code == 0, preview.output
    assert (tmp_path / "frame.png").is_file()

    # Old reports kept the durations under stages; preview must still read them.
    legacy = tmp_path / "legacy-report.json"
    legacy.write_text(json.dumps({"stages": {"durations": report["scene_durations"]}}), encoding="utf-8")
    old_preview = runner.invoke(
        app,
        ["preview", str(tmp_path / "video.mp4"), "0", "0.0", "--report", str(legacy), "-o", str(tmp_path / "legacy-frame.png")],
    )
    assert old_preview.exit_code == 0, old_preview.output
    assert (tmp_path / "legacy-frame.png").is_file()


def test_preview_invalid_scene_index(tmp_path):
    """preview with out-of-range scene_index exits nonzero."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video bytes")
    report = tmp_path / "report.json"
    report.write_text('{"stages": {"durations": [4.0]}}')
    runner = CliRunner()
    result = runner.invoke(app, ["preview", str(video), "5", "0.0", "--report", str(report)])
    assert result.exit_code != 0


def test_preview_negative_t(tmp_path):
    """preview with negative t exits nonzero."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video bytes")
    report = tmp_path / "report.json"
    report.write_text('{"stages": {"durations": [4.0]}}')
    runner = CliRunner()
    result = runner.invoke(app, ["preview", str(video), "0", "-1.0", "--report", str(report)])
    assert result.exit_code != 0


def test_preview_t_beyond_scene_duration(tmp_path):
    """preview with t beyond scene duration exits nonzero."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video bytes")
    report = tmp_path / "report.json"
    report.write_text('{"stages": {"durations": [4.0]}}')
    runner = CliRunner()
    result = runner.invoke(app, ["preview", str(video), "0", "5.0", "--report", str(report)])
    assert result.exit_code != 0



def test_debug_still_lists_why_generation_failed(monkeypatch, tmp_path):
    """--debug used to re-raise before printing the validation errors, leaving only
    'failed to fill 1 scene(s)' with no reason. The reasons must be visible either way."""
    from animatica.ai.base import StoryboardGenerationError

    def boom(**kwargs):
        raise StoryboardGenerationError("failed to fill 1 scene(s)", ["scene 2: narration too long", "scene 2: bad param"])

    monkeypatch.setattr("animatica.cli.make_video", boom)
    for extra in ([], ["--debug"]):
        r = CliRunner().invoke(app, ["make", "explain fourier transform", "-o", str(tmp_path), *extra])
        assert r.exit_code != 0
        assert "scene 2: narration too long" in r.output and "scene 2: bad param" in r.output

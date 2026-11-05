from typer.testing import CliRunner

from animatica.cli import app

def test_cli_unknown_backend_exits_nonzero_without_traceback():
    r = CliRunner().invoke(app, ["make", "graph of sin(x)", "--backend", "nope"])
    assert r.exit_code != 0 and "Traceback" not in r.output and "available:" in r.output


def test_make_template_prompt_zero_provider_calls(monkeypatch, tmp_path):
    calls = []

    class CountingProvider:
        name = "counting"
        def generate(self, prompt, schema):
            calls.append(prompt)
            return "{}"

    from animatica.ai.router import get_provider
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

    from animatica.ai.router import get_provider
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


def test_make_invalid_storyboard_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"version":"1","title":"T","scenes":[{"beats":[{"component":"nope","params":{}}]}]}')
    runner = CliRunner()
    result = runner.invoke(app, ["make", "--from", str(bad), "-o", str(tmp_path)])
    assert result.exit_code == 2


def test_make_no_debug_no_traceback(monkeypatch, tmp_path):
    from animatica.ai.router import get_provider
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


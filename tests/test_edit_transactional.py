"""Tests for transactional `animatica edit`: originals preserved on failure."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from animatica.ai.base import StoryboardGenerationError
from animatica.cli import app
from animatica.pipeline import MakeResult
from animatica.storyboard.models import Storyboard


def _make_valid_storyboard() -> Storyboard:
    """Create a minimal valid storyboard."""
    return Storyboard.model_validate(
        {
            "version": "1",
            "title": "Original",
            "scenes": [
                {"beats": [{"component": "title_card", "params": {"title": "Original"}}]}
            ],
        }
    )


# ---------------------------------------------------------------------------
# Provider failure → originals preserved
# ---------------------------------------------------------------------------

def test_edit_provider_failure_preserves_originals(tmp_path: Path, monkeypatch):
    """When the provider fails, original storyboard/video/report are unchanged."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    (out_dir / "video.mp4").write_bytes(b"original video")
    (out_dir / "report.json").write_text('{"original": true}')
    (out_dir / "unrelated.txt").write_text("unrelated content")

    def fake_generate(*args, **kwargs):
        raise StoryboardGenerationError("provider failed", ["provider error"])

    monkeypatch.setattr("animatica.ai.repair.generate_storyboard", fake_generate)

    runner = CliRunner()
    result = runner.invoke(
        app, ["edit", str(out_dir), "change title", "--provider", "nim"]
    )

    assert result.exit_code == 1
    # Originals unchanged
    assert (
        out_dir / "storyboard.json"
    ).read_text() == '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    assert (out_dir / "video.mp4").read_bytes() == b"original video"
    assert (out_dir / "report.json").read_text() == '{"original": true}'
    assert (out_dir / "unrelated.txt").read_text() == "unrelated content"


# ---------------------------------------------------------------------------
# Validation failure → originals preserved
# ---------------------------------------------------------------------------

def test_edit_validation_failure_preserves_originals(tmp_path: Path, monkeypatch):
    """When validation fails, originals are unchanged."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    (out_dir / "video.mp4").write_bytes(b"original video")
    (out_dir / "report.json").write_text('{"original": true}')

    # Valid storyboard returned by generator, but registry.validate returns errors
    monkeypatch.setattr(
        "animatica.ai.repair.generate_storyboard",
        lambda *a, **k: _make_valid_storyboard(),
    )

    class FakeReg:
        names = lambda self: ["title_card"]

        def validate(self, sb):
            return ["field 'title': too long"]

    monkeypatch.setattr("animatica.components.registry.default_registry", lambda: FakeReg())

    runner = CliRunner()
    result = runner.invoke(
        app, ["edit", str(out_dir), "change title", "--provider", "nim"]
    )

    assert result.exit_code == 1
    assert (
        out_dir / "storyboard.json"
    ).read_text() == '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    assert (out_dir / "video.mp4").read_bytes() == b"original video"
    assert (out_dir / "report.json").read_text() == '{"original": true}'


# ---------------------------------------------------------------------------
# Renderer failure → originals preserved
# ---------------------------------------------------------------------------

def test_edit_renderer_failure_preserves_originals(tmp_path: Path, monkeypatch):
    """When rendering fails, original storyboard/video/report are unchanged."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    (out_dir / "video.mp4").write_bytes(b"original video")
    (out_dir / "report.json").write_text('{"original": true}')
    (out_dir / "unrelated.txt").write_text("unrelated content")

    monkeypatch.setattr(
        "animatica.ai.repair.generate_storyboard",
        lambda *a, **k: _make_valid_storyboard(),
    )

    def fake_make_video(*args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr("animatica.pipeline.make_video", fake_make_video)

    runner = CliRunner()
    result = runner.invoke(
        app, ["edit", str(out_dir), "change title", "--provider", "nim"]
    )

    assert result.exit_code == 1
    # Originals unchanged
    assert (
        out_dir / "storyboard.json"
    ).read_text() == '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    assert (out_dir / "video.mp4").read_bytes() == b"original video"
    assert (out_dir / "report.json").read_text() == '{"original": true}'
    assert (out_dir / "unrelated.txt").read_text() == "unrelated content"


# ---------------------------------------------------------------------------
# Successful edit → new artifacts, unrelated preserved
# ---------------------------------------------------------------------------

def test_edit_success_promotes_and_preserves(tmp_path: Path, monkeypatch):
    """On success, new artifacts replace olds; unrelated files are preserved."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    (out_dir / "video.mp4").write_bytes(b"original video")
    (out_dir / "report.json").write_text('{"original": true}')
    (out_dir / "captions.vtt").write_text("WEBVTT\n\noriginal caption\n")
    (out_dir / "unrelated.txt").write_text("unrelated content")
    (out_dir / "media").mkdir()
    (out_dir / "media" / "old.png").write_bytes(b"old media")

    new_sb = _make_valid_storyboard()
    new_sb.title = "Edited Title"
    monkeypatch.setattr(
        "animatica.ai.repair.generate_storyboard",
        lambda *a, **k: new_sb,
    )

    def fake_make_video(storyboard_path=None, out_dir=None, preview=False, **kwargs):
        staging = Path(out_dir)
        (staging / "storyboard.json").write_text(
            '{"version":"1","title":"Edited Title","scenes":[{"beats":[{"component":"title_card","params":{"title":"Edited Title"}}]}]}'
        )
        (staging / "video.mp4").write_bytes(b"new video")
        (staging / "report.json").write_text('{"new": true}')
        (staging / "captions.vtt").write_text("WEBVTT\n\nnew caption\n")
        (staging / "media").mkdir(exist_ok=True)
        (staging / "media" / "new.png").write_bytes(b"new media")
        return MakeResult(
            video=staging / "video.mp4",
            storyboard=staging / "storyboard.json",
            captions=staging / "captions.vtt",
            report=staging / "report.json",
            warnings=[],
        )

    monkeypatch.setattr("animatica.pipeline.make_video", fake_make_video)

    runner = CliRunner()
    result = runner.invoke(
        app, ["edit", str(out_dir), "change title", "--provider", "nim"]
    )

    assert result.exit_code == 0, f"edit failed: {result.output}"
    # New storyboard
    assert "Edited Title" in (out_dir / "storyboard.json").read_text()
    # New video
    assert (out_dir / "video.mp4").read_bytes() == b"new video"
    # New report
    assert '"new": true' in (out_dir / "report.json").read_text()
    # New captions
    assert "new caption" in (out_dir / "captions.vtt").read_text()
    # New media
    assert (out_dir / "media" / "new.png").read_bytes() == b"new media"
    # Old media removed
    assert not (out_dir / "media" / "old.png").exists()
    # Unrelated file preserved
    assert (out_dir / "unrelated.txt").read_text() == "unrelated content"


# ---------------------------------------------------------------------------
# No provider available → clean error, originals untouched
# ---------------------------------------------------------------------------

def test_edit_no_provider_preserves_originals(tmp_path: Path, monkeypatch):
    """When no provider is configured, error is clean and originals untouched."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    (out_dir / "video.mp4").write_bytes(b"original video")

    monkeypatch.setattr("animatica.ai.router.get_provider", lambda *a, **k: None)

    runner = CliRunner()
    result = runner.invoke(app, ["edit", str(out_dir), "change title"])

    assert result.exit_code == 1
    assert "no AI provider available" in result.output
    assert (
        out_dir / "storyboard.json"
    ).read_text() == '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    assert (out_dir / "video.mp4").read_bytes() == b"original video"


# ---------------------------------------------------------------------------
# Missing storyboard.json → clean error
# ---------------------------------------------------------------------------

def test_edit_no_storyboard_file(tmp_path: Path):
    """When out_dir has no storyboard.json, clean error."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["edit", str(out_dir), "change title"])

    assert result.exit_code == 1
    assert "no storyboard.json" in result.output.lower()

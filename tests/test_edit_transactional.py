"""Tests for transactional `animatica edit`: originals preserved on failure."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from animatica.ai.base import StoryboardGenerationError
from animatica.cli import app
from animatica.pipeline import MakeResult, make_video
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
    # Patch generate_storyboard where edit_cmd imports it from (line 508 of
    # cli.py): `from animatica.ai.repair import generate_storyboard`. This
    # resolves from animatica.ai.repair at call time, so patching that source
    # module works. Patching animatica.cli.generate_storyboard does NOT work
    # because it's a local name inside edit_cmd, not a module attribute.
    monkeypatch.setattr(
        "animatica.ai.repair.generate_storyboard",
        lambda *a, **k: new_sb,
    )
    # Patch get_provider so the test reaches the render branch; the provider
    # object itself is never used by fake_make_video.
    monkeypatch.setattr(
        "animatica.ai.router.get_provider",
        lambda *a, **k: "fake-provider",
    )

    # Patch make_video where edit_cmd imports it from (line 511 of cli.py):
    # `from animatica.pipeline import MakeResult, make_video`. Same rationale
    # as above.
    orig_make_video = make_video
    def fake_make_video(storyboard_path=None, out_dir=None, preview=False, **kwargs):
        staging = Path(out_dir)
        (staging / "storyboard.json").write_text(
            "{\"version\":\"1\",\"title\":\"Edited Title\",\"scenes\":[{\"beats\":[{\"component\":\"title_card\",\"params\":{\"title\":\"Edited Title\"}}]}]}"
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

    try:
        runner = CliRunner()
        result = runner.invoke(
            app, ["edit", str(out_dir), "change title", "--provider", "nim", "--replace"]
        )
    finally:
        monkeypatch.setattr("animatica.pipeline.make_video", orig_make_video)

    assert result.exit_code == 0, f"edit failed: {result.output}"
    # Backups are PRESERVED after success (recoverable promotion).
    # They are NOT removed, so the user can recover if the promotion was unexpected.
    # Verify by looking for the backup directory.
    import glob as _glob
    backup_dirs = _glob.glob(str(out_dir.parent / "*.edit-backup-*"))
    assert len(backup_dirs) == 1, f"expected 1 backup dir, found {len(backup_dirs)}"
    backup_dir = Path(backup_dirs[0])
    # Originals were backed up (and then replaced)
    assert "Original" in (backup_dir / "storyboard.json").read_text()
    # New artifacts replaced originals
    assert "Edited Title" in (out_dir / "storyboard.json").read_text()
    assert (out_dir / "video.mp4").read_bytes() == b"new video"
    assert '"new": true' in (out_dir / "report.json").read_text()
    assert "new caption" in (out_dir / "captions.vtt").read_text()
    assert (out_dir / "media" / "new.png").read_bytes() == b"new media"
    # Old media removed
    assert not (out_dir / "media" / "old.png").exists()
    # Unrelated file preserved
    assert (out_dir / "unrelated.txt").read_text() == "unrelated content"
    # The patch of the CLI module's make_video is not visible to the
    # edit command because edit_cmd imported `make_video` from
    # animatica.pipeline at module load time. This is a known limitation
    # of the test infrastructure, but the edit command's behavior is
    # verified by the artifacts in out_dir (new storyboard title, etc.).


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


# ---------------------------------------------------------------------------
# Default path: staging directory is used directly as output (no rename,
# no copy, no check-then-act race). Pre-existing directories are never
# deleted or overwritten.
# ---------------------------------------------------------------------------

def test_edit_default_path_uses_staging_directly(tmp_path: Path, monkeypatch):
    """Default path: the mkdtemp staging dir becomes the output directly.
    No rename, no copy, no pre-existing directory is ever deleted."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    (out_dir / "video.mp4").write_bytes(b"original video")

    # Pre-create a sibling directory that would collide if we used a
    # predictable name. With mkdtemp-as-output, this directory is simply
    # ignored (we never look at it).
    collision_dir = out_dir.parent / "out.edited-collision"
    collision_dir.mkdir()
    (collision_dir / "keep.txt").write_text("pre-existing content")

    new_sb = _make_valid_storyboard()
    new_sb.title = "Edited Title"
    monkeypatch.setattr("animatica.ai.repair.generate_storyboard", lambda *a, **k: new_sb)
    monkeypatch.setattr("animatica.ai.router.get_provider", lambda *a, **k: "fake-provider")

    orig_make_video = make_video
    def fake_make_video(storyboard_path=None, out_dir=None, preview=False, **kwargs):
        staging = Path(out_dir)
        (staging / "storyboard.json").write_text(
            "{\"version\":\"1\",\"title\":\"Edited Title\"}"
        )
        (staging / "video.mp4").write_bytes(b"new video")
        return MakeResult(
            video=staging / "video.mp4",
            storyboard=staging / "storyboard.json",
            captions=staging / "captions.vtt",
            report=staging / "report.json",
            warnings=[],
        )
    monkeypatch.setattr("animatica.pipeline.make_video", fake_make_video)

    try:
        runner = CliRunner()
        result = runner.invoke(app, ["edit", str(out_dir), "change title", "--provider", "nim"])
    finally:
        monkeypatch.setattr("animatica.pipeline.make_video", orig_make_video)

    assert result.exit_code == 0, f"edit failed: {result.output}"
    # Original out_dir untouched
    assert (out_dir / "storyboard.json").read_text().count("Original") >= 1
    assert (out_dir / "video.mp4").read_bytes() == b"original video"
    # Collision directory NOT deleted (we never touched it)
    assert (collision_dir / "keep.txt").read_text() == "pre-existing content"
    # New output is the staging dir (animatica-edit-*), alongside out_dir
    out_dir_parent = out_dir.parent
    staging_dirs = [d for d in out_dir_parent.iterdir()
                    if d.is_dir() and d.name.startswith("animatica-edit-")]
    assert len(staging_dirs) >= 1, (
        f"expected at least one animatica-edit- dir, found {list(out_dir_parent.iterdir())}"
    )
    # The Video path points inside the staging dir
    assert "Video:" in result.output
    # Verify the video file exists inside the staging dir
    for sd in staging_dirs:
        if (sd / "video.mp4").is_file():
            assert (sd / "video.mp4").read_bytes() == b"new video"
            break
    else:
        raise AssertionError("no staging dir contains video.mp4")


# ---------------------------------------------------------------------------
# Missing original artifacts → edit still succeeds when some originals absent
# ---------------------------------------------------------------------------

def test_edit_missing_original_artifacts(tmp_path: Path, monkeypatch):
    """Default path: when original video/report/captions/media are missing,
    edit still succeeds and creates new artifacts without error."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    # No video.mp4, report.json, captions.vtt, or media/ originally.

    new_sb = _make_valid_storyboard()
    new_sb.title = "Edited Title"
    monkeypatch.setattr("animatica.ai.repair.generate_storyboard", lambda *a, **k: new_sb)
    monkeypatch.setattr("animatica.ai.router.get_provider", lambda *a, **k: "fake-provider")

    orig_make_video = make_video
    def fake_make_video(storyboard_path=None, out_dir=None, preview=False, **kwargs):
        staging = Path(out_dir)
        (staging / "storyboard.json").write_text(
            "{\"version\":\"1\",\"title\":\"Edited Title\"}"
        )
        (staging / "video.mp4").write_bytes(b"new video")
        return MakeResult(
            video=staging / "video.mp4",
            storyboard=staging / "storyboard.json",
            captions=staging / "captions.vtt",
            report=staging / "report.json",
            warnings=[],
        )
    monkeypatch.setattr("animatica.pipeline.make_video", fake_make_video)

    try:
        runner = CliRunner()
        result = runner.invoke(app, ["edit", str(out_dir), "change title", "--provider", "nim"])
    finally:
        monkeypatch.setattr("animatica.pipeline.make_video", orig_make_video)

    assert result.exit_code == 0, f"edit failed: {result.output}"
    # New artifact directory created alongside original
    out_dir_parent = out_dir.parent
    staging_dirs = [d for d in out_dir_parent.iterdir()
                    if d.is_dir() and d.name.startswith("animatica-edit-")]
    assert len(staging_dirs) >= 1, f"expected at least one animatica-edit- directory, found {list(out_dir_parent.iterdir())}"
    # Original storyboard untouched
    assert (out_dir / "storyboard.json").read_text().count("Original") >= 1


# ---------------------------------------------------------------------------
# --replace rollback: newly created artifacts are removed on failure
# ---------------------------------------------------------------------------

def test_replace_rollback_removes_newly_created_artifact(tmp_path: Path, monkeypatch):
    """--replace rollback removes artifacts that didn't exist before promotion.

    out_dir has storyboard.json but NO video.mp4. Promotion copies storyboard.json
    (backed up first) and creates video.mp4 (newly created). If the video.mp4 copy
    fails, rollback restores storyboard.json from backup and removes video.mp4.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    # No video.mp4 originally — it will be newly created by promotion.

    new_sb = _make_valid_storyboard()
    new_sb.title = "Edited Title"
    monkeypatch.setattr("animatica.ai.repair.generate_storyboard", lambda *a, **k: new_sb)
    monkeypatch.setattr("animatica.ai.router.get_provider", lambda *a, **k: "fake-provider")

    orig_make_video = make_video
    def fake_make_video(storyboard_path=None, out_dir=None, preview=False, **kwargs):
        staging = Path(out_dir)
        (staging / "storyboard.json").write_text('{"version":"1","title":"Edited Title"}')
        (staging / "video.mp4").write_bytes(b"new video")
        return MakeResult(
            video=staging / "video.mp4",
            storyboard=staging / "storyboard.json",
            captions=staging / "captions.vtt",
            report=staging / "report.json",
            warnings=[],
        )
    monkeypatch.setattr("animatica.pipeline.make_video", fake_make_video)

    # Fail on copying video.mp4 (destination path contains "video.mp4").
    import shutil
    original_copy2 = shutil.copy2
    def failing_copy2(src, dst, *args, **kwargs):
        if "video.mp4" in str(dst):
            raise OSError("simulated copy failure on video.mp4")
        return original_copy2(src, dst, *args, **kwargs)
    monkeypatch.setattr("shutil.copy2", failing_copy2)

    try:
        runner = CliRunner()
        result = runner.invoke(app, ["edit", str(out_dir), "change title", "--provider", "nim", "--replace"])
    finally:
        monkeypatch.setattr("animatica.pipeline.make_video", orig_make_video)
        monkeypatch.setattr("shutil.copy2", original_copy2)

    assert result.exit_code != 0, f"edit should fail when promotion fails: {result.output}"
    # storyboard.json was backed up and restored to original
    assert "Original" in (out_dir / "storyboard.json").read_text()
    # video.mp4 was newly created and should be removed on rollback
    assert not (out_dir / "video.mp4").exists(), "newly created video.mp4 should be removed on rollback"
    # Backup dir preserved for manual recovery
    import glob as _glob
    backup_dirs = _glob.glob(str(out_dir.parent / "*.edit-backup-*"))
    assert len(backup_dirs) >= 1, f"expected backup dir, found {list(out_dir_parent.iterdir()) if (out_dir_parent := out_dir.parent) else []}"


def test_replace_rollback_removes_new_media_directory(tmp_path: Path, monkeypatch):
    """--replace rollback removes a newly created media directory if promotion fails.

    out_dir has no media/ directory. Promotion creates media/ with new files.
    If media copy fails, rollback removes the newly created media/ directory.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "storyboard.json").write_text(
        '{"version":"1","title":"Original","scenes":[{"beats":[{"component":"title_card","params":{"title":"Original"}}]}]}'
    )
    # No media/ originally — it will be newly created by promotion.

    new_sb = _make_valid_storyboard()
    new_sb.title = "Edited Title"
    monkeypatch.setattr("animatica.ai.repair.generate_storyboard", lambda *a, **k: new_sb)
    monkeypatch.setattr("animatica.ai.router.get_provider", lambda *a, **k: "fake-provider")

    orig_make_video = make_video
    def fake_make_video(storyboard_path=None, out_dir=None, preview=False, **kwargs):
        staging = Path(out_dir)
        (staging / "storyboard.json").write_text('{"version":"1","title":"Edited Title"}')
        (staging / "video.mp4").write_bytes(b"new video")
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

    # Fail on copying media directory.
    import shutil
    original_copytree = shutil.copytree
    def failing_copytree(src, dst, *args, **kwargs):
        if "media" in str(dst):
            raise OSError("simulated copytree failure on media")
        return original_copytree(src, dst, *args, **kwargs)
    monkeypatch.setattr("shutil.copytree", failing_copytree)

    try:
        runner = CliRunner()
        result = runner.invoke(app, ["edit", str(out_dir), "change title", "--provider", "nim", "--replace"])
    finally:
        monkeypatch.setattr("animatica.pipeline.make_video", orig_make_video)
        monkeypatch.setattr("shutil.copytree", original_copytree)

    assert result.exit_code != 0, f"edit should fail when promotion fails: {result.output}"
    # storyboard.json was backed up and restored to original
    assert "Original" in (out_dir / "storyboard.json").read_text()
    # Newly created media/ should be removed on rollback
    assert not (out_dir / "media").exists(), "newly created media/ should be removed on rollback"
    # Backup dir preserved for manual recovery
    import glob as _glob
    backup_dirs = _glob.glob(str(out_dir.parent / "*.edit-backup-*"))
    assert len(backup_dirs) >= 1, f"expected backup dir"

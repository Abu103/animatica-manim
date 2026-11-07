"""Headless tests for the Animatica TUI using Textual's pilot testing.

These tests exercise screen navigation, input validation, and the
offline template path without rendering a real video.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from animatica.cli import app as cli_app
from animatica.tui import AnimaticaTuiApp, TuiSettings, run_tui


# ---------------------------------------------------------------------------
# Module-level checks
# ---------------------------------------------------------------------------


def test_tui_module_imports():
    """The tui module imports cleanly (textual is installed in this env)."""
    from animatica.tui import AnimaticaTuiApp  # noqa: F401
    assert AnimaticaTuiApp is not None


def test_tui_settings_defaults():
    """TuiSettings has sensible defaults."""
    s = TuiSettings()
    assert s.provider == "template"
    assert s.quality == "preview"
    assert s.orientation == "landscape"
    assert s.theme == "dark-blue"
    assert s.captions is True
    assert s.frame_lint is False
    assert s.vertical is False


def test_tui_command_registered():
    """The 'tui' CLI command is registered."""
    cmd_names = [c.name for c in cli_app.registered_commands if c.name]
    assert "tui" in cmd_names


def test_tui_command_help():
    """The tui command shows help text."""
    runner = CliRunner()
    result = runner.invoke(cli_app, ["tui", "--help"])
    assert result.exit_code == 0
    assert "Terminal User Interface" in result.output or "textual" in result.output


def test_tui_missing_textual_error(monkeypatch):
    """run_tui raises ImportError if textual is not installed."""
    import animatica.tui as tui_mod
    import builtins

    original_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name == "textual":
            raise ImportError("No module named 'textual'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocking_import)
    with pytest.raises(ImportError, match="textual"):
        run_tui()


# ---------------------------------------------------------------------------
# TUI screen tests (headless, using Textual pilot)
# ---------------------------------------------------------------------------


def _make_tui_app():
    """Create an AnimaticaTuiApp and return its Textual app for run_test."""
    wrapper = AnimaticaTuiApp()
    return wrapper.create_app(), wrapper


async def _run_test_with_size(app, size=(100, 50)):
    """Run app with a larger virtual screen so all widgets are visible."""
    return app.run_test(size=size)


def _q(app, selector, *types):
    """Query a widget on the currently active screen."""
    return app.screen.query_one(selector, *types)


def _text(widget) -> str:
    """Get text content from a widget (Static uses .content in Textual 8.x)."""
    return str(getattr(widget, "content", ""))


@pytest.mark.tui
async def test_welcome_screen_shows_widgets():
    """Welcome screen displays prompt input, template select, provider select."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test() as pilot:
        await pilot.pause()

        # Welcome screen should be active
        assert _q(textual_app, "#prompt-input") is not None
        assert _q(textual_app, "#template-select") is not None
        assert _q(textual_app, "#provider-select") is not None
        assert _q(textual_app, "#sb-path-input") is not None


@pytest.mark.tui
async def test_welcome_empty_prompt_shows_error():
    """Clicking Next with no input shows an error message."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test() as pilot:
        await pilot.pause()

        next_btn = _q(textual_app, "#next")
        await pilot.click(next_btn)
        await pilot.pause()

        status = _q(textual_app, "#welcome-status")
        assert "Please enter" in _text(status)


@pytest.mark.tui
async def test_welcome_prompt_navigates_to_settings():
    """Entering a prompt and clicking Next advances to Settings screen."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test() as pilot:
        await pilot.pause()

        prompt_input = _q(textual_app, "#prompt-input")
        await pilot.click(prompt_input)
        prompt_input.value = "test prompt"
        await pilot.pause()

        next_btn = _q(textual_app, "#next")
        await pilot.click(next_btn)
        await pilot.pause()

        # Should now be on settings screen
        assert _q(textual_app, "#output-dir") is not None
        assert _q(textual_app, "#quality-select") is not None


@pytest.mark.tui
async def test_settings_navigates_to_review():
    """Settings screen Next advances to Review screen."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()

        # Quickly fill welcome and go to settings
        prompt_input = _q(textual_app, "#prompt-input")
        await pilot.click(prompt_input)
        prompt_input.value = "hello world"
        await pilot.pause()
        await pilot.click(_q(textual_app, "#next"))
        await pilot.pause()

        # On settings screen
        next_btn = _q(textual_app, "#next")
        await pilot.click(next_btn)
        await pilot.pause()

        # Should now be on review screen
        assert _q(textual_app, "#review-summary") is not None
        assert _q(textual_app, "#start") is not None


@pytest.mark.tui
async def test_review_shows_settings_summary():
    """Review screen displays the collected settings."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()

        # Navigate to review
        prompt_input = _q(textual_app, "#prompt-input")
        await pilot.click(prompt_input)
        prompt_input.value = "hello world"
        await pilot.pause()
        await pilot.click(_q(textual_app, "#next"))
        await pilot.pause()
        await pilot.click(_q(textual_app, "#next"))
        await pilot.pause()

        summary = _q(textual_app, "#review-summary")
        text = _text(summary)
        assert "hello world" in text
        assert "preview" in text.lower()


@pytest.mark.tui
async def test_review_warns_on_existing_outputs(tmp_path):
    """Review screen warns when output files already exist."""
    textual_app, _ = _make_tui_app()
    textual_app.settings.output_dir = tmp_path
    textual_app.settings.prompt = "test"
    (tmp_path / "video.mp4").write_bytes(b"fake")

    async with textual_app.run_test() as pilot:
        await pilot.pause()

        # Skip straight to review by pushing screens
        textual_app.push_screen("review")
        await pilot.pause()

        warn = _q(textual_app, "#review-warning")
        text = _text(warn)
        assert "video.mp4" in text


@pytest.mark.tui
async def test_settings_back_returns_to_welcome():
    """Settings screen Back returns to Welcome screen."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()

        # Go to settings
        prompt_input = _q(textual_app, "#prompt-input")
        await pilot.click(prompt_input)
        prompt_input.value = "test"
        await pilot.pause()
        await pilot.click(_q(textual_app, "#next"))
        await pilot.pause()

        # Go back
        back_btn = _q(textual_app, "#back")
        await pilot.click(back_btn)
        await pilot.pause()

        assert _q(textual_app, "#prompt-input") is not None


# ---------------------------------------------------------------------------
# Offline template path
# ---------------------------------------------------------------------------


@pytest.mark.tui
def test_template_matcher_provides_offline_options():
    """TemplateMatcher returns offline templates for common prompts."""
    from animatica.ai.template import TemplateMatcher

    matcher = TemplateMatcher()
    templates = matcher.list_templates()
    assert len(templates) > 0
    # Common prompts should match
    assert matcher.match("make a title card about hello") is not None
    assert matcher.match("graph of sin(x)") is not None
    assert matcher.match("steps to bake a cake") is not None


# ---------------------------------------------------------------------------
# Progress screen: cancelled render stops cleanly
# ---------------------------------------------------------------------------


@pytest.mark.tui
async def test_progress_cancel_stops_render(tmp_path, monkeypatch):
    """Cancelling a render stops the worker and shows cancelled state."""
    textual_app, wrapper = _make_tui_app()
    textual_app.settings.output_dir = tmp_path
    textual_app.settings.prompt = "test"
    textual_app.settings.provider = "template"
    textual_app.settings.storyboard_path = None

    # Mock make_video to block until cancelled, then complete
    import animatica.tui as tui_mod

    blocked = asyncio.Event()
    released = asyncio.Event()

    def blocking_make_video(*args, **kwargs):
        blocked.wait(timeout=2)
        released.set()
        # Return a fake result
        result = MagicMock()
        result.video = tmp_path / "video.mp4"
        result.storyboard = tmp_path / "storyboard.json"
        result.report = tmp_path / "report.json"
        result.captions = tmp_path / "captions.vtt"
        result.warnings = []
        return result

    monkeypatch.setattr(tui_mod, "make_video", blocking_make_video)

    async with textual_app.run_test() as pilot:
        await pilot.pause()

        # Push progress screen directly
        textual_app.push_screen("progress")
        await pilot.pause()

        # Cancel immediately
        cancel_btn = _q(textual_app, "#cancel")
        await pilot.click(cancel_btn)
        await pilot.pause()

        # Should show cancelling then stopped
        status = _q(textual_app, "#progress-status")
        text = _text(status)
        assert "Cancelling" in text or "Cancelled" in text or "stopped" in text

        # Release the blocked render
        blocked.set()
        await pilot.pause()

        await asyncio.sleep(0.5)
        # Check render thread is done
        if textual_app._render_thread is not None:
            textual_app._render_thread.join(timeout=5)
        assert not textual_app._render_thread.is_alive()


# ---------------------------------------------------------------------------
# Real offline render integration test
# ---------------------------------------------------------------------------


@pytest.mark.tui
@pytest.mark.render
async def test_real_offline_render(tmp_path):
    """Render a real offline preview video via the pipeline.

    Uses a checked-in gallery storyboard and preview quality so it is fast.
    This is the "real offline preview render" verification.
    """
    from animatica.pipeline import make_video

    # Use the sine gallery storyboard (simple, fast to render)
    sb_path = Path("acceptance/gallery/sine/storyboard.json")
    assert sb_path.is_file(), f"Gallery storyboard not found: {sb_path}"

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "out",
        preview=True,
    )

    assert result.video.is_file(), f"Video not produced: {result.video}"
    assert result.video.stat().st_size > 0, "Video is empty"
    assert result.report.is_file(), f"Report not produced: {result.report}"
    assert result.storyboard.is_file(), f"Storyboard not produced: {result.storyboard}"

    # No parametric-graph fallback warnings
    import json as _json
    report = _json.loads(result.report.read_text(encoding="utf-8"))
    warnings = report.get("warnings", [])
    pg_warnings = [w for w in warnings if "parametric_graph" in str(w).lower()]
    assert pg_warnings == [], f"parametric_graph fallback warnings: {pg_warnings}"

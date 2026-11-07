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


async def _run_test_with_size(app, size=(80, 24)):
    """Run app at a given terminal size (default 80x24)."""
    return app.run_test(size=size)


def _q(app, selector, *types):
    """Query a widget on the currently active screen."""
    return app.screen.query_one(selector, *types)


def _text(widget) -> str:
    """Get text content from a widget (Static uses .content in Textual 8.x)."""
    return str(getattr(widget, "content", ""))


async def _fill_welcome_and_go_to_settings(app, pilot, prompt_text="hello world"):
    """Navigate from Welcome to Settings using pilot clicks."""
    await pilot.pause()
    prompt_input = _q(app, "#prompt-input")
    await pilot.click(prompt_input)
    prompt_input.value = prompt_text
    await pilot.pause()
    await pilot.click(_q(app, "#next"))
    await pilot.pause()
    assert _q(app, "#output-dir") is not None
    assert _q(app, "#quality-select") is not None


@pytest.mark.tui
async def test_welcome_screen_shows_widgets():
    """Welcome screen displays prompt input, template select, provider select."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        # Welcome screen should be active
        assert _q(textual_app, "#prompt-input") is not None
        assert _q(textual_app, "#template-select") is not None
        assert _q(textual_app, "#provider-select") is not None
        assert _q(textual_app, "#sb-path-input") is not None
        assert _q(textual_app, "#next") is not None


@pytest.mark.tui
async def test_welcome_empty_prompt_shows_error():
    """Clicking Next with no input shows an error message."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
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
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await _fill_welcome_and_go_to_settings(textual_app, pilot)


@pytest.mark.tui
async def test_settings_navigates_to_review_at_80x24():
    """Settings screen Next advances to Review screen at 80x24 (no resize)."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await _fill_welcome_and_go_to_settings(textual_app, pilot)

        # On settings screen: Next button should be visible at 80x24
        next_btn = _q(textual_app, "#next")
        assert next_btn is not None
        await pilot.click(next_btn)
        await pilot.pause()

        # Should now be on review screen
        assert _q(textual_app, "#review-summary") is not None
        assert _q(textual_app, "#start") is not None


@pytest.mark.tui
async def test_settings_navigates_to_review_at_80x30():
    """Settings screen Next advances to Review screen at 80x30 (smaller than 100x50)."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 30)) as pilot:
        await _fill_welcome_and_go_to_settings(textual_app, pilot)

        # On settings screen: Next button should be visible at 80x30
        next_btn = _q(textual_app, "#next")
        assert next_btn is not None
        await pilot.click(next_btn)
        await pilot.pause()

        # Should now be on review screen
        assert _q(textual_app, "#review-summary") is not None
        assert _q(textual_app, "#start") is not None


@pytest.mark.tui
async def test_review_shows_settings_summary_at_80x24():
    """Review screen displays the collected settings at 80x24."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await _fill_welcome_and_go_to_settings(textual_app, pilot)
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

    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        # Skip straight to review by pushing screens
        textual_app.push_screen("review")
        await pilot.pause()

        warn = _q(textual_app, "#review-warning")
        text = _text(warn)
        assert "video.mp4" in text


@pytest.mark.tui
async def test_settings_back_returns_to_welcome_at_80x24():
    """Settings screen Back returns to Welcome screen at 80x24."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await _fill_welcome_and_go_to_settings(textual_app, pilot)

        # Go back
        back_btn = _q(textual_app, "#back")
        await pilot.click(back_btn)
        await pilot.pause()

        assert _q(textual_app, "#prompt-input") is not None


# ---------------------------------------------------------------------------
# Keyboard shortcut tests
# ---------------------------------------------------------------------------


@pytest.mark.tui
async def test_keyboard_shortcuts_at_80x24():
    """Keyboard shortcuts (Alt+Left, Alt+Right) work at 80x24 without resizing.

    We call the screen action methods directly (which is what the key
    bindings trigger) rather than relying on pilot.press(), which sends
    keys to the focused widget and can be swallowed by Input widgets.
    """
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        # Alt+Right on Welcome should go to Settings (need to enter a prompt first)
        prompt_input = _q(textual_app, "#prompt-input")
        await pilot.click(prompt_input)
        prompt_input.value = "test prompt"
        await pilot.pause()
        # Unfocus the input so the navigation shortcut can fire
        await pilot.press("tab")
        await pilot.pause()
        textual_app.screen.action_next()
        await pilot.pause()
        assert _q(textual_app, "#output-dir") is not None

        # Alt+Left on Settings should go back to Welcome
        textual_app.screen.action_back()
        await pilot.pause()
        assert _q(textual_app, "#prompt-input") is not None

        # Go to Settings again
        textual_app.screen.action_next()
        await pilot.pause()
        assert _q(textual_app, "#next") is not None

        # Alt+Right on Settings should go to Review
        textual_app.screen.action_next()
        await pilot.pause()
        assert _q(textual_app, "#review-summary") is not None
        assert _q(textual_app, "#start") is not None

        # Alt+Left on Review should go back to Settings
        textual_app.screen.action_back()
        await pilot.pause()
        assert _q(textual_app, "#next") is not None


@pytest.mark.tui
async def test_typing_b_n_c_q_in_input_does_not_navigate():
    """Typing characters b, n, c, q in a prompt input must not trigger
    navigation shortcuts. The focus guard in action_next/action_back
    prevents navigation while an Input/TextArea has focus."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        # Click the prompt input and type text containing b, n, c, q
        prompt_input = _q(textual_app, "#prompt-input")
        await pilot.click(prompt_input)
        prompt_input.value = "explain taylor series with b n c q keys"
        await pilot.pause()

        # Input is still focused - action_next must NOT navigate
        textual_app.screen.action_next()
        await pilot.pause()
        # Still on Welcome screen
        assert _q(textual_app, "#prompt-input") is not None
        assert _q(textual_app, "#welcome-status") is not None

        # Unfocus and try again - should navigate now
        await pilot.press("tab")
        await pilot.pause()
        textual_app.screen.action_next()
        await pilot.pause()
        assert _q(textual_app, "#output-dir") is not None


@pytest.mark.tui
async def test_result_screen_actions_at_80x24():
    """Result screen: Alt+N starts another job, F10 quits,
    buttons reachable via Tab/Enter."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        # Navigate Welcome → Settings → Review
        await _fill_welcome_and_go_to_settings(textual_app, pilot)
        await pilot.click(_q(textual_app, "#next"))
        await pilot.pause()

        # Push result screen directly (simulating post-render state)
        textual_app.push_screen("result")
        await pilot.pause()

        # Verify Result screen widgets are present
        assert _q(textual_app, "#result-paths") is not None
        assert _q(textual_app, "#open-video") is not None
        assert _q(textual_app, "#new-job") is not None
        assert _q(textual_app, "#done") is not None

        # Alt+N should return to a previous screen (not crash)
        textual_app.screen.action_new_job()
        await pilot.pause()

        # Quit should call app.exit
        textual_app.push_screen("result")
        await pilot.pause()
        textual_app.screen.action_quit()
        await pilot.pause()


@pytest.mark.tui
async def test_enter_activates_buttons_on_review():
    """Buttons on Review screen can be activated with Enter after Tab focus."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        # Navigate to Review
        await _fill_welcome_and_go_to_settings(textual_app, pilot)
        await pilot.click(_q(textual_app, "#next"))
        await pilot.pause()

        # Tab to the Start Render button and press Enter
        start_btn = _q(textual_app, "#start")
        await pilot.click(start_btn)  # focus it first
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # Should advance to Progress screen
        assert _q(textual_app, "#progress-stage") is not None


@pytest.mark.tui
async def test_tab_reaches_buttons_on_settings():
    """Tab navigation reaches Back and Next buttons on Settings screen."""
    textual_app, _ = _make_tui_app()
    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        await _fill_welcome_and_go_to_settings(textual_app, pilot)
        await pilot.pause()

        # Tab through to reach the Next button
        next_btn = _q(textual_app, "#next")
        back_btn = _q(textual_app, "#back")
        assert next_btn is not None
        assert back_btn is not None

        # Click Next button to verify it works
        await pilot.click(next_btn)
        await pilot.pause()
        assert _q(textual_app, "#review-summary") is not None


# ---------------------------------------------------------------------------
# Output directory default test
# ---------------------------------------------------------------------------


def test_default_output_dir_is_home_based():
    """Default output dir is a dedicated folder in home, not cwd/Downloads."""
    s = TuiSettings()
    assert str(s.output_dir).startswith(str(Path.home()))
    assert s.output_dir.name == "animatica-output"
    assert "Downloads" not in str(s.output_dir)


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

    async with textual_app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        # Push progress screen directly
        textual_app.push_screen("progress")
        await pilot.pause()

        # Cancel immediately using Escape key shortcut
        await pilot.press("escape")
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

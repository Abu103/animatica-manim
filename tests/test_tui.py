"""Headless tests for the Animatica studio TUI (Textual pilot).

These drive the real app at 80x24, which is the smallest terminal we promise to
support. Nothing here renders a video: ``make_video`` is replaced by a fake.
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from animatica.ai.template import TemplateMatcher
from animatica.cli import app as cli_app
from animatica.pipeline import MakeResult
from animatica.storyboard.models import dump_storyboard
from animatica.tui import AnimaticaTuiApp, TuiSettings, run_tui


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app():
    wrapper = AnimaticaTuiApp()
    return wrapper.create_app(), wrapper


def _q(app, selector, *types):
    return app.query_one(selector, *types)


def _text(widget) -> str:
    return str(getattr(widget, "content", ""))


def _status(app) -> str:
    return _text(_q(app, "#status"))


async def _click(app, pilot, selector: str) -> bool:
    """Click a visible point inside a control, scrolling pane controls first.

    Pilot.click defaults to offset (0, 0), which may be clipped in a scroll
    pane. Find a point that Textual itself hit-tests as this widget (or one of
    its children) so the click stays within the visible part of the control.
    """
    widget = _q(app, selector)
    if selector not in {"#next", "#back"}:
        widget.scroll_visible(animate=False)
        await pilot.pause()

    region = widget.region
    screen = app.screen.size.region
    left, top = max(region.x, screen.x), max(region.y, screen.y)
    right, bottom = min(region.right, screen.right), min(region.bottom, screen.bottom)
    if left >= right or top >= bottom:
        raise AssertionError(f"{selector} has no on-screen area after scrolling: {region!r}")

    center_x, center_y = (left + right) // 2, (top + bottom) // 2
    points = sorted(
        ((x, y) for y in range(top, bottom) for x in range(left, right)),
        key=lambda point: abs(point[0] - center_x) + abs(point[1] - center_y),
    )
    click_offset = None
    descendant_offset = None
    for x, y in points:
        under_pointer, _ = app.get_widget_at(x, y)
        if under_pointer is widget:
            click_offset = (x - region.x, y - region.y)
            break
        current = under_pointer
        while current is not None:
            if current is widget:
                if descendant_offset is None:
                    descendant_offset = (x - region.x, y - region.y)
                break
            current = current.parent
    if click_offset is None:
        click_offset = descendant_offset
    if click_offset is None:
        raise AssertionError(f"{selector} has no visible hit-test point in {region!r}")

    clicked = await pilot.click(widget, offset=click_offset)
    await pilot.pause()
    return clicked


async def _press(app, pilot, selector: str) -> None:
    """Activate a button through its own press() instead of pointer geometry.

    Tests of what a button *does* should not depend on where the terminal
    renders it; Windows runners hit-test the mouse differently. Real click
    behaviour is covered by the explicit click tests.
    """
    widget = _q(app, selector)
    widget.scroll_visible(top=True, animate=False)
    await pilot.pause()
    assert not widget.disabled, f"{selector} is disabled"
    widget.press()
    await pilot.pause()


async def _start_with_template(app, pilot, template_name: str) -> None:
    _q(app, "#source-mode").value = "template"
    _q(app, "#template-select").value = template_name
    await _settle(pilot)
    await _click(app, pilot, "#next")
    await _settle(pilot)


async def _open_advanced_json(app, pilot) -> None:
    _q(app, "#storyboard-advanced").collapsed = False
    await _settle(pilot)


async def _advance_to_render(app, pilot) -> None:
    while _q(app, "#steps").current != "pane-render":
        await _click(app, pilot, "#next")
        await _settle(pilot)


async def _settle(pilot, turns: int = 3) -> None:
    for _ in range(turns):
        await pilot.pause()


async def _wait_for(app, pilot, predicate, timeout: float = 15.0) -> bool:
    """Poll the app until predicate() is true (workers run off the UI thread)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await pilot.pause()
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return False


def _fake_result(tmp_path: Path, warnings: list[str] | None = None) -> MakeResult:
    return MakeResult(
        video=tmp_path / "video.mp4",
        storyboard=tmp_path / "storyboard.json",
        captions=tmp_path / "captions.vtt",
        report=tmp_path / "report.json",
        warnings=warnings or [],
    )


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_tui_module_imports():
    from animatica.tui import AnimaticaTuiApp as cls

    assert cls is not None


def test_tui_settings_defaults():
    s = TuiSettings()
    assert s.provider == "template"
    assert s.quality == "preview"
    assert s.orientation == "landscape"
    assert s.theme == "dark-blue"
    assert s.captions is True
    assert s.frame_lint is False
    assert s.vertical is False


def test_tui_command_registered():
    assert "tui" in [c.name for c in cli_app.registered_commands if c.name]


def test_tui_command_help():
    result = CliRunner().invoke(cli_app, ["tui", "--help"])
    assert result.exit_code == 0
    assert "Terminal User Interface" in result.output or "textual" in result.output


def test_tui_missing_textual_error(monkeypatch):
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
# Layout
# ---------------------------------------------------------------------------


@pytest.mark.tui
async def test_prompt_step_has_its_controls_at_80x24():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert _q(app, "#prompt-input") is not None
        assert _q(app, "#template-select") is not None
        assert _q(app, "#sb-path-input") is not None
        assert _q(app, "#next") is not None
        assert _q(app, "#tagline").display is False
        assert "01 / 04" in _text(_q(app, "#topbar-step"))
        assert "Ready" in _status(app)


@pytest.mark.tui
async def test_job_step_exposes_options_at_80x24():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app._goto("job")
        await _settle(pilot)
        for selector in (
            "#output-dir",
            "#quality-select",
            "#theme-select",
            "#orientation-select",
            "#provider-select",
            "#captions-switch",
            "#frame-lint-switch",
        ):
            assert _q(app, selector) is not None, selector
        advanced = _q(app, "#job-advanced")
        assert advanced.collapsed is True
        assert app.query("#job-advanced #output-dir").nodes, "output path stays in More options"
        assert str(app.settings.output_dir) in _text(_q(app, "#output-summary"))
        assert _q(app, "#output-summary").region.bottom <= 19


@pytest.mark.tui
async def test_more_options_disclosure_opens_by_click_at_80x24():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app._goto("job")
        await _settle(pilot)
        advanced = _q(app, "#job-advanced")
        assert advanced.collapsed is True
        await _click(app, pilot, "#job-advanced CollapsibleTitle")
        assert advanced.collapsed is False


@pytest.mark.tui
async def test_switches_and_selects_write_through_to_settings():
    app, wrapper = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        _q(app, "#captions-switch").value = False
        _q(app, "#quality-select").value = "high"
        await _settle(pilot)

        assert wrapper.settings.captions is False
        assert wrapper.settings.quality == "high"


@pytest.mark.tui
async def test_wizard_shell_shows_one_step_and_obvious_navigation_at_80x24():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        steps = _q(app, "#steps")
        assert steps.__class__.__name__ == "ContentSwitcher"
        assert steps.current == "pane-prompt"
        assert _q(app, "#pane-storyboard").display is False
        assert _q(app, "#back").disabled is True
        assert _q(app, "#next").display is True
        assert "IDEA" in _text(_q(app, "#topbar-step")).upper()
        assert _q(app, "#next").region.bottom == _q(app, "#step-nav").region.bottom
        assert _q(app, "#step-nav").region.bottom == _q(app, "#status").region.y
        assert _q(app, "#status").region.bottom == _q(app, "Footer").region.y

        async def press_step(key: str, expected: str) -> None:
            await pilot.press(key)
            assert await _wait_for(app, pilot, lambda: steps.current == expected), (
                f"{key} did not navigate to {expected}; current={steps.current!r}"
            )

        _q(app, "#prompt-input").value = "explain tides"
        await press_step("ctrl+j", "pane-storyboard")
        assert _q(app, "#back").disabled is False
        await press_step("ctrl+j", "pane-job")
        await press_step("ctrl+j", "pane-render")
        assert _q(app, "#next").display is False
        assert _q(app, "#start").display is True
        await press_step("ctrl+b", "pane-job")
        await press_step("ctrl+b", "pane-storyboard")
        await press_step("ctrl+b", "pane-prompt")


@pytest.mark.tui
async def test_alternate_sources_are_hidden_until_chosen():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        source_modes = app.query("#source-mode").nodes
        assert source_modes, "the input type should be visible and explicit"
        source_mode = source_modes[0]
        assert source_mode.value == "prompt"
        assert _q(app, "#prompt-input").display is True
        assert _q(app, "#template-select").display is False
        assert _q(app, "#sb-path-input").display is False

        source_mode.value = "template"
        await _settle(pilot)
        assert _q(app, "#prompt-input").display is False
        assert _q(app, "#template-select").display is True
        assert _q(app, "#sb-path-input").display is False

        source_mode.value = "storyboard"
        await _settle(pilot)
        assert _q(app, "#prompt-input").display is False
        assert _q(app, "#template-select").display is False
        assert _q(app, "#sb-path-input").display is True


@pytest.mark.tui
async def test_help_opens_from_keyboard_and_escape_closes_it():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await _settle(pilot)
        assert app.screen.query("#help-copy").nodes
        await pilot.press("escape")
        await _settle(pilot)
        assert app.screen.id == "_default"

        await _click(app, pilot, "#topbar-help")
        await _settle(pilot)
        assert app.screen.query("#help-copy").nodes
        await pilot.click(app.screen.query_one("#close-help"))
        await _settle(pilot)
        assert app.screen.id == "_default"


@pytest.mark.tui
async def test_raw_storyboard_json_is_behind_collapsed_advanced_section():
    from textual.widgets import Collapsible

    app, _ = _make_app()
    template_name = TemplateMatcher().list_templates()[0][0]
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.query("#source-mode").nodes, "source mode must be explicit"
        await _start_with_template(app, pilot, template_name)
        advanced = _q(app, "#storyboard-advanced", Collapsible)
        assert advanced.collapsed is True
        assert _q(app, "#storyboard-json") is not None
        await _click(app, pilot, "#storyboard-advanced CollapsibleTitle")
        assert advanced.collapsed is False


# ---------------------------------------------------------------------------
# Prompt validation
# ---------------------------------------------------------------------------


@pytest.mark.tui
async def test_empty_prompt_is_rejected_with_a_reason():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await _click(app, pilot, "#next")
        await _settle(pilot)

        assert "Write a topic" in _text(_q(app, "#prompt-status"))
        assert "error" in _q(app, "#status").classes


@pytest.mark.tui
async def test_explicit_source_mode_ignores_unselected_hidden_values():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        _q(app, "#prompt-input").value = "explain tides"
        _q(app, "#sb-path-input").value = "/tmp/nope.json"
        await _click(app, pilot, "#next")
        await _settle(pilot)

        assert _q(app, "#steps").current == "pane-storyboard"
        assert app.storyboard is None
        assert app.settings.prompt == "explain tides"
        assert _q(app, "#storyboard-empty").display is True
        assert "error" not in _q(app, "#status").classes


@pytest.mark.tui
async def test_missing_storyboard_file_is_reported(tmp_path):
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        _q(app, "#source-mode").value = "storyboard"
        _q(app, "#sb-path-input").value = str(tmp_path / "absent.json")
        await _settle(pilot)
        await _click(app, pilot, "#next")
        await _settle(pilot)

        assert "Not found" in _text(_q(app, "#prompt-status"))
        assert "not found" in _status(app).lower()


@pytest.mark.tui
async def test_storyboard_file_mode_loads_quoted_path_and_preserves_display(tmp_path):
    template_name = TemplateMatcher().list_templates()[0][0]
    storyboard = TemplateMatcher().by_name(template_name)
    assert storyboard is not None
    path = tmp_path / "ready.json"
    dump_storyboard(storyboard, path)

    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        _q(app, "#source-mode").value = "storyboard"
        quoted_path = f'"{path}"'
        _q(app, "#sb-path-input").value = quoted_path
        await _settle(pilot)
        await _click(app, pilot, "#next")
        await _settle(pilot)

        assert app.storyboard is not None
        assert app.storyboard.title == storyboard.title
        assert app.settings.storyboard_path == path
        assert _q(app, "#sb-path-input").value == quoted_path
        assert _q(app, "#storyboard-table").row_count > 0
        assert "file: ready.json" in _text(_q(app, "#side-source"))


@pytest.mark.tui
async def test_typing_does_not_navigate():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        _q(app, "#prompt-input").focus()
        await pilot.press(*"explain entropy")
        await _settle(pilot)

        assert _q(app, "#prompt-input") is not None  # still on step 1
        assert "01 / 04" in _text(_q(app, "#topbar-step"))


# ---------------------------------------------------------------------------
# Storyboard step
# ---------------------------------------------------------------------------


@pytest.mark.tui
async def test_template_loads_a_storyboard_into_the_table():
    app, _ = _make_app()
    template_name = TemplateMatcher().list_templates()[0][0]
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert _q(app, "#tagline").display is True
        await _start_with_template(app, pilot, template_name)

        table = _q(app, "#storyboard-table")
        assert app.storyboard is not None
        assert table.row_count == sum(len(scene.beats) for scene in app.storyboard.scenes)
        assert table.row_count >= 1
        first = table.get_row_at(0)
        assert first[0] == "Scene 1"
        assert "Title Card" in first[1]
        assert [column.label.plain for column in table.columns.values()] == [
            "Scene", "Visual", "Narration"
        ]
        assert "template:" in _text(_q(app, "#side-source"))
        assert "scenes" in _text(_q(app, "#storyboard-summary"))
        assert _q(app, "#steps").current == "pane-storyboard"


@pytest.mark.tui
async def test_storyboard_json_edit_validates_and_updates_the_table():
    app, _ = _make_app()
    template_name = TemplateMatcher().list_templates()[0][0]
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await _start_with_template(app, pilot, template_name)
        await _open_advanced_json(app, pilot)

        editor = _q(app, "#storyboard-json")
        payload = json.loads(editor.text)
        payload["scenes"][0]["beats"][0]["caption"] = "Edited caption"
        editor.text = json.dumps(payload)
        clicked = True
        await _press(app, pilot, "#validate")
        status = _q(app, "#storyboard-status")
        assert await _wait_for(app, pilot, lambda: "Valid" in _text(status)), (
            f"Validate click hit target={clicked}; expected a valid storyboard status; "
            f"pane={_text(status)!r}, app_status={_status(app)!r}"
        )
        assert "validated" in _status(app).lower()


@pytest.mark.tui
async def test_broken_json_is_reported_not_raised():
    app, _ = _make_app()
    template_name = TemplateMatcher().list_templates()[0][0]
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await _start_with_template(app, pilot, template_name)
        await _open_advanced_json(app, pilot)

        _q(app, "#storyboard-json").text = '{"version": "1", '
        clicked = True
        await _press(app, pilot, "#validate")
        status = _q(app, "#storyboard-status")
        assert await _wait_for(app, pilot, lambda: "JSON error" in _text(status)), (
            f"Validate click hit target={clicked}; expected the JSON error status; "
            f"pane={_text(status)!r}, app_status={_status(app)!r}"
        )
        assert "not valid JSON" in _status(app)


@pytest.mark.tui
async def test_unknown_component_is_rejected_by_the_registry():
    app, _ = _make_app()
    template_name = TemplateMatcher().list_templates()[0][0]
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await _start_with_template(app, pilot, template_name)
        await _open_advanced_json(app, pilot)

        editor = _q(app, "#storyboard-json")
        editor.text = editor.text.replace("title_card", "not_a_component", 1)
        clicked = True
        await _press(app, pilot, "#validate")
        status = _q(app, "#storyboard-status")
        assert await _wait_for(app, pilot, lambda: "problem" in _text(status)), (
            f"Validate click hit target={clicked}; expected component-validation problems; "
            f"pane={_text(status)!r}, app_status={_status(app)!r}"
        )
        assert "cannot render" in _status(app)


@pytest.mark.tui
async def test_existing_outputs_are_flagged_before_rendering(tmp_path):
    (tmp_path / "video.mp4").write_bytes(b"old")
    (tmp_path / "report.json").write_text("{}")
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app._goto("job")
        _q(app, "#output-dir").value = str(tmp_path)
        await _settle(pilot)

        warning = _text(_q(app, "#overwrite-warning"))
        assert "Will overwrite" in warning
        assert "video.mp4" in warning
        region = _q(app, "#overwrite-warning").region
        assert region.y >= 3 and region.bottom <= 19, "warning must be visible before Continue"


# ---------------------------------------------------------------------------
# Render step (make_video is faked)
# ---------------------------------------------------------------------------


@pytest.mark.tui
async def test_render_bar_shows_real_units_from_the_pipeline(tmp_path, monkeypatch):
    """The bar counts scene/post units the pipeline reports, not ticking time."""
    from animatica.progress import ProgressEvent

    result = _fake_result(tmp_path)
    step1, step2 = threading.Event(), threading.Event()

    def fake_make_video(**kwargs):
        report = kwargs["on_progress"]
        report(ProgressEvent(stage="storyboard", label="resolving storyboard", done=0, total=0))
        step1.wait(timeout=10)  # main thread inspects the still-unknown bar
        for done in range(1, 4):
            report(ProgressEvent(stage="render", label=f"scene {done}/3: done", done=done, total=4))
        report(ProgressEvent(stage="captions", label="writing captions and report", done=4, total=4))
        step2.wait(timeout=10)  # main thread inspects 4/4 before the run finishes
        return result

    monkeypatch.setattr("animatica.tui.make_video", fake_make_video)

    app, wrapper = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await _settle(pilot)
        _q(app, "#prompt-input").value = "explain entropy"
        await _settle(pilot)
        app._goto("render")
        await _settle(pilot)
        await _click(app, pilot, "#start")

        # unknown amount of work: no percentage until a real unit arrives
        assert await _wait_for(app, pilot, lambda: _q(app, "#progress-bar").total is None)
        step1.set()

        assert await _wait_for(app, pilot, lambda: _q(app, "#progress-bar").progress == 4)
        bar = _q(app, "#progress-bar")
        assert bar.total == 4, "total must be the units the pipeline really has"
        assert "writing captions" in _text(_q(app, "#render-stage"))
        step2.set()

        assert await _wait_for(app, pilot, lambda: "done" in _text(_q(app, "#status")).lower())
        bar = _q(app, "#progress-bar")
        assert (bar.total, bar.progress) == (4, 4), "the real unit scale survives completion"


async def test_render_bar_stays_indeterminate_while_work_is_unknown(tmp_path, monkeypatch):
    """A pipeline that reports nothing must not show a made-up percentage."""
    result = _fake_result(tmp_path)
    gate = threading.Event()

    def fake_make_video(**kwargs):
        gate.wait(timeout=10)
        return result

    monkeypatch.setattr("animatica.tui.make_video", fake_make_video)

    app, wrapper = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await _settle(pilot)
        _q(app, "#prompt-input").value = "explain entropy"
        await _settle(pilot)
        app._goto("render")
        await _settle(pilot)
        await _click(app, pilot, "#start")

        assert await _wait_for(app, pilot, lambda: _q(app, "#cancel").disabled is False)
        assert _q(app, "#progress-bar").total is None
        gate.set()
        assert await _wait_for(app, pilot, lambda: "done" in _text(_q(app, "#status")).lower())


async def test_typed_prompt_reaches_the_job_settings_live():
    """Regression: Start used to read a cached prompt and say "nothing to render"."""
    app, wrapper = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(pilot)
        _q(app, "#prompt-input").value = "explain why the sky is blue"
        await _settle(pilot)

        assert app.settings.prompt == "explain why the sky is blue"


async def test_start_from_the_render_step_uses_the_typed_prompt(monkeypatch):
    """The Render step is reachable directly, so Start must read the prompt field."""
    calls = []

    def fake_make_video(**kwargs):
        calls.append(kwargs)
        return _fake_result()

    monkeypatch.setattr("animatica.tui.make_video", fake_make_video)
    app, wrapper = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await _settle(pilot)
        _q(app, "#prompt-input").value = "explain why the sky is blue"
        await _settle(pilot)
        app._goto("render")
        await _settle(pilot)
        await _click(app, pilot, "#start")

        assert await _wait_for(app, pilot, lambda: bool(calls))
        assert calls[0]["prompt"] == "explain why the sky is blue"


async def test_render_completes_and_shows_the_video(tmp_path, monkeypatch):
    result = _fake_result(tmp_path, warnings=["safe_area: caption close to the edge"])
    monkeypatch.setattr("animatica.tui.make_video", lambda **kwargs: result)

    app, wrapper = _make_app()
    template_name = TemplateMatcher().list_templates()[0][0]
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        _q(app, "#output-dir").value = str(tmp_path)
        await _start_with_template(app, pilot, template_name)
        await _advance_to_render(app, pilot)
        await _click(app, pilot, "#start")

        assert await _wait_for(app, pilot, lambda: _text(_q(app, "#render-stage")) == "Complete.")
        assert str(tmp_path / "video.mp4") in _text(_q(app, "#render-summary"))
        assert "warning" in _text(_q(app, "#render-summary"))
        assert _q(app, "#open-video").disabled is False
        assert _q(app, "#progress-bar").progress == 100
        assert app.result is not None


@pytest.mark.tui
async def test_render_failure_is_logged_and_does_not_crash(tmp_path, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("ffmpeg fell over")

    monkeypatch.setattr("animatica.tui.make_video", boom)

    app, _ = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        _q(app, "#prompt-input").value = "explain entropy"
        await _click(app, pilot, "#next")
        await _settle(pilot)
        await _advance_to_render(app, pilot)
        await _click(app, pilot, "#start")

        assert await _wait_for(app, pilot, lambda: "failed" in _text(_q(app, "#status")).lower())
        assert "Render failed" in _text(_q(app, "#render-stage"))
        assert _q(app, "#start").disabled is False  # can try again


@pytest.mark.tui
async def test_render_details_copy_button_and_shortcut_copy_plain_error(monkeypatch):
    app, _ = _make_app()
    copied = []
    error = "OSError: [WinError 123] invalid path: '\"D:\\animatica\"'"

    async with app.run_test(size=(80, 24)) as pilot:
        monkeypatch.setattr(app, "copy_to_clipboard", copied.append)
        app._goto("render")
        await _settle(pilot)
        app._render_failed("Render failed", [error])
        await _settle(pilot)

        copy_button = _q(app, "#copy-render-log")
        assert copy_button.disabled is False
        assert copy_button.region.width > 0
        await _click(app, pilot, "#copy-render-log")
        expected = f"Render failed\n  {error}"
        assert copied[-1] == expected
        assert "copied" in _status(app).lower()

        await pilot.press("ctrl+shift+c")
        await _settle(pilot)
        assert copied[-1] == expected


@pytest.mark.tui
async def test_quoted_output_path_is_normalized_for_use_but_preserved_for_display():
    app, _ = _make_app()

    async with app.run_test(size=(80, 24)) as pilot:
        output = _q(app, "#output-dir")
        output.value = r'"D:\animatica"'
        await _settle(pilot)

        assert app.settings.output_dir == Path(r"D:\animatica")
        assert output.value == r'"D:\animatica"'
        assert '"' not in _text(_q(app, "#output-summary"))


@pytest.mark.tui
async def test_cancel_requests_a_stop_and_reports_it(tmp_path, monkeypatch):
    release = threading.Event()

    def slow(**kwargs):
        release.wait(5)
        return _fake_result(tmp_path)

    monkeypatch.setattr("animatica.tui.make_video", slow)

    app, _ = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        _q(app, "#prompt-input").value = "explain entropy"
        await _click(app, pilot, "#next")
        await _settle(pilot)
        await _advance_to_render(app, pilot)
        await _click(app, pilot, "#start")
        await pilot.pause()

        assert _q(app, "#cancel").disabled is False
        await _click(app, pilot, "#cancel")
        await _settle(pilot)
        assert app.cancel_event.is_set()

        release.set()
        assert await _wait_for(app, pilot, lambda: _text(_q(app, "#render-stage")) == "Cancelled.")
        assert "cancelled" in _status(app).lower()


@pytest.mark.tui
async def test_nothing_to_render_is_refused():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.action_start_render()
        await _settle(pilot)

        assert "Nothing to render" in _status(app)


@pytest.mark.tui
async def test_ctrl_j_advances_one_step_from_idea_to_scenes():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        _q(app, "#prompt-input").value = "explain tides"
        await pilot.press("ctrl+j")
        await _settle(pilot)

        assert _q(app, "#steps").current == "pane-storyboard"
        assert "prompt" in _text(_q(app, "#side-source"))


@pytest.mark.tui
async def test_ctrl_b_goes_back_a_step():
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        _q(app, "#prompt-input").value = "explain tides"
        await pilot.press("ctrl+j")
        await _settle(pilot)
        await pilot.press("ctrl+b")
        await _settle(pilot)

        assert _q(app, "#steps").current == "pane-prompt"


# ---------------------------------------------------------------------------
# Defaults: the Job step is the only place users configure anything, and the
# choices stick for the next launch.
# ---------------------------------------------------------------------------


def _picker(app, widget_id):
    from animatica.tui_picker import FilterSelect

    return _q(app, f"#{widget_id}", FilterSelect)


async def test_job_step_uses_searchable_pickers(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIMATICA_CONFIG_DIR", str(tmp_path))
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        for widget_id in ("quality-select", "theme-select", "provider-select", "orientation-select"):
            picker = _picker(app, widget_id)
            assert picker._options, f"{widget_id} has no choices"
            assert picker.value, f"{widget_id} starts without a value"


async def test_typing_in_a_picker_filters_and_commits(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIMATICA_CONFIG_DIR", str(tmp_path))
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app._goto("job")
        await _settle(pilot)
        quality = _picker(app, "quality-select")
        search = quality.query_one("#fs-input")
        app.set_focus(search)
        await pilot.pause()
        assert app.focused is search, "quality search input was not focused"
        await pilot.press("h", "i")
        assert await _wait_for(
            app, pilot, lambda: [label for label, _ in quality._filtered] == ["High 1080p"]
        ), f"quality filter did not converge: {quality._filtered!r}"
        await pilot.press("enter")
        assert await _wait_for(app, pilot, lambda: quality.value == "high"), (
            f"quality selection was not committed: {quality.value!r}"
        )
    assert app.settings.quality == "high"


async def test_choices_are_remembered_for_the_next_session(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIMATICA_CONFIG_DIR", str(tmp_path))
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app._goto("job")
        await _settle(pilot)
        _q(app, "#job-advanced").collapsed = False
        await _settle(pilot)
        theme = _picker(app, "theme-select")
        search = theme.query_one("#fs-input")
        app.set_focus(search)
        await pilot.pause()
        assert app.focused is search, "theme search input was not focused"
        await pilot.press("l", "i", "g")  # -> Light
        assert await _wait_for(
            app, pilot, lambda: [label for label, _ in theme._filtered] == ["Light"]
        ), f"theme filter did not converge: {theme._filtered!r}"
        await pilot.press("enter")
        assert await _wait_for(app, pilot, lambda: theme.value == "light"), (
            f"theme selection was not committed: {theme.value!r}"
        )
        assert await _wait_for(app, pilot, lambda: app.settings.theme == "light"), (
            f"app setting was not updated: {app.settings.theme!r}"
        )
    assert app.settings.theme == "light"

    from animatica.config import load_config

    saved_config = tmp_path / "config.toml"
    assert saved_config.is_file(), f"config was not written: {saved_config}"
    assert load_config().theme == "light", saved_config.read_text(encoding="utf-8")

    fresh = TuiSettings()
    assert fresh.theme == "light"


async def test_saved_defaults_survive_a_broken_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIMATICA_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.toml").write_text("this is not toml = = =\n", encoding="utf-8")
    fresh = TuiSettings()  # must fall back to built-in defaults, not raise
    assert fresh.quality in {"preview", "standard", "high"}


@pytest.mark.tui
async def test_picker_enter_commits_first_match_when_highlight_is_stale():
    """Enter must pick the first match even if the list highlight lags or is out of range."""
    app, _ = _make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        theme = _picker(app, "theme-select")
        search = theme.query_one("#fs-input")
        app.set_focus(search)
        await pilot.pause()
        search.value = "lig"
        assert await _wait_for(
            app, pilot, lambda: [label for label, _ in theme._filtered] == ["Light"]
        ), f"filter did not converge: {theme._filtered!r}"

        theme._list().highlighted = None  # simulate a lagging highlight
        search.post_message(search.Submitted(search, search.value))
        assert await _wait_for(app, pilot, lambda: theme.value == "light"), theme.value
        assert app.settings.theme == "light"

"""Animatica Terminal User Interface (TUI).

A guided, full-screen workflow for creating explainer videos.

Requires the optional ``textual`` package:

    pip install "animatica[tui]"

The TUI reuses the existing :func:`animatica.pipeline.make_video` pipeline
rather than duplicating rendering logic.  It is gated behind a lazy import of
``textual`` so the ordinary CLI works without it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from animatica.ai.base import ProviderError, RateLimited, StoryboardGenerationError
from animatica.ai.router import get_provider
from animatica.ai.template import TemplateMatcher
from animatica.components.registry import default_registry
from animatica.config import Config, load_config, load_key
from animatica.pipeline import MakeResult, make_video
from animatica.storyboard.models import Storyboard, dump_storyboard, load_storyboard


# ---------------------------------------------------------------------------
# Lazy import of Textual.  This module imports cleanly without textual
# installed; the TUI command itself raises a helpful error if it is missing.
# ---------------------------------------------------------------------------


def _import_textual() -> dict[str, Any]:
    """Import textual modules, raising a clear error if unavailable."""
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Container, Horizontal, Vertical, VerticalScroll
        from textual.screen import Screen
        from textual.widgets import (
            Button,
            Checkbox,
            Footer,
            Header,
            Input,
            Label,
            ProgressBar,
            Select,
            Static,
            TextArea,
        )
        return {
            "App": App,
            "Button": Button,
            "Checkbox": Checkbox,
            "ComposeResult": ComposeResult,
            "Container": Container,
            "Footer": Footer,
            "Header": Header,
            "Horizontal": Horizontal,
            "Input": Input,
            "Label": Label,
            "ProgressBar": ProgressBar,
            "Select": Select,
            "Static": Static,
            "TextArea": TextArea,
            "Vertical": Vertical,
            "VerticalScroll": VerticalScroll,
            "Screen": Screen,
        }
    except ImportError as exc:
        raise ImportError(
            "The 'tui' command requires the optional 'textual' package. "
            "Install it with:  pip install 'animatica[tui]'"
        ) from exc


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_QUALITY = "preview"
DEFAULT_ORIENTATION = "landscape"
DEFAULT_THEME = "dark-blue"
DEFAULT_PROVIDER = "template"  # offline by default: no API key needed
DEFAULT_FRAME_LINT = False
DEFAULT_CAPTIONS = True

QUALITY_CHOICES = [
    ("Preview (480p15)", "preview"),
    ("Standard (720p)", "standard"),
    ("High (1080p)", "high"),
]
ORIENTATION_CHOICES = [
    ("Landscape (16:9)", "landscape"),
    ("Portrait (9:16)", "portrait"),
]
THEME_CHOICES = [
    ("Dark Blue", "dark-blue"),
    ("Light", "light"),
    ("High Contrast", "high-contrast"),
]
PROVIDER_CHOICES = [
    ("Template (offline, no API key)", "template"),
    ("NVIDIA NIM (Nemotron)", "nim"),
    ("Groq", "groq"),
    ("OpenRouter", "openrouter"),
    ("Ollama (local)", "ollama"),
]

# Checked-in gallery storyboards usable offline.
GALLERY_DIR = Path(__file__).resolve().parents[2] / "acceptance" / "gallery"
GALLERY_CHOICES: list[tuple[str, str]] = []
if GALLERY_DIR.is_dir():
    for entry in sorted(GALLERY_DIR.iterdir()):
        if entry.is_dir() and (entry / "storyboard.json").exists():
            GALLERY_CHOICES.append((entry.name.title(), str(entry)))

# Default output location: a dedicated folder in the user's home directory,
# never the current working directory (which might be Downloads).
DEFAULT_OUTPUT_DIR = Path.home() / "animatica-output"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TuiSettings:
    """Mutable settings collected as the user walks through the TUI."""

    def __init__(self) -> None:
        self.prompt: str = ""
        self.storyboard_path: Path | None = None
        self.provider: str = DEFAULT_PROVIDER
        self.model: str | None = None
        self.output_dir: Path = DEFAULT_OUTPUT_DIR
        self.quality: str = DEFAULT_QUALITY
        self.orientation: str = DEFAULT_ORIENTATION
        self.theme: str = DEFAULT_THEME
        self.frame_lint: bool = DEFAULT_FRAME_LINT
        self.captions: bool = DEFAULT_CAPTIONS
        self._template_storyboard: Storyboard | None = None

    @property
    def vertical(self) -> bool:
        return self.orientation == "portrait"

    def existing_outputs(self) -> list[str]:
        """Names of output artifacts that already exist in output_dir."""
        found: list[str] = []
        for name in ("storyboard.json", "video.mp4", "captions.vtt", "report.json"):
            if (self.output_dir / name).is_file():
                found.append(name)
        if (self.output_dir / "media").is_dir():
            found.append("media/")
        return found


# ---------------------------------------------------------------------------
# The App (built lazily when textual is available)
# ---------------------------------------------------------------------------


class AnimaticaTuiApp:
    """Wrapper that builds and runs the Textual application."""

    def __init__(self) -> None:
        self.w = _import_textual()
        self.settings = TuiSettings()
        self._result: MakeResult | None = None
        self._cancel_event = threading.Event()
        self._render_thread: threading.Thread | None = None
        self._render_error: str | None = None
        self._poll_interval: Any = None
        self._screens = self._build_screens()
        self._App = self.w["App"]
        self._Screen = self.w["Screen"]

    # -- screen construction ------------------------------------------------

    def _build_screens(self) -> dict[str, type]:
        w = self.w
        settings = self.settings

        class WelcomeScreen(w["Screen"]):
            BINDINGS = [
                ("alt+right", "next", "Next"),
            ]

            def compose(self) -> w["ComposeResult"]:
                yield w["Header"]()
                yield w["Footer"]()
                with w["Vertical"](id="welcome-container"):
                    yield w["Label"]("Animatica", classes="title")
                    yield w["Label"]("Prompt-to-explainer-video TUI", classes="subtitle")
                    yield w["Label"]("Enter a prompt or pick a starting point:", classes="prompt-label")
                    yield w["Input"](placeholder="e.g. explain the pythagorean theorem", id="prompt-input")
                    yield w["Label"]("Or choose an offline template:", classes="prompt-label")
                    tmpl_opts = [(name, name) for name, _ in TemplateMatcher().list_templates()]
                    yield w["Select"](options=tmpl_opts, allow_blank=True, id="template-select")
                    yield w["Label"]("Or open an existing storyboard.json:", classes="prompt-label")
                    yield w["Input"](placeholder="/path/to/storyboard.json", id="sb-path-input")
                    yield w["Label"]("Provider / model:", classes="prompt-label")
                    yield w["Select"](
                        options=PROVIDER_CHOICES, value=DEFAULT_PROVIDER, id="provider-select"
                    )
                    yield w["Button"]("Next →", id="next", variant="primary")
                    yield w["Static"]("", id="welcome-status")

            def on_button_pressed(self, event: w["Button"].Pressed) -> None:
                if event.button.id == "next":
                    self._go_next()

            def action_next(self) -> None:
                # Don't navigate if the user is typing in an input field
                focused = self.app.focused
                if isinstance(focused, (w["Input"], w["TextArea"])):
                    return
                self._go_next()

            def _go_next(self) -> None:
                prompt_input = self.query_one("#prompt-input", w["Input"])
                sb_input = self.query_one("#sb-path-input", w["Input"])
                provider_select = self.query_one("#provider-select", w["Select"])
                template_select = self.query_one("#template-select", w["Select"])
                status = self.query_one("#welcome-status", w["Static"])

                prompt = prompt_input.value.strip()
                sb_path_str = sb_input.value.strip()
                provider = (
                    str(provider_select.value) if provider_select.value else DEFAULT_PROVIDER
                )
                # Select.NULL is truthy, so check explicitly for blank selection
                template_value = template_select.value
                template_name = (
                    str(template_value)
                    if template_value not in (None, w["Select"].NULL)
                    else None
                )

                sources = sum(bool(x) for x in (prompt, sb_path_str, template_name))
                if sources == 0:
                    status.update("Please enter a prompt, pick a template, or open a storyboard.")
                    return
                if sources > 1:
                    status.update("Please use only one source (prompt, template, or storyboard).")
                    return

                app = self.app
                app.settings.prompt = prompt
                app.settings.provider = provider
                app.settings._template_storyboard = None

                if sb_path_str:
                    p = Path(sb_path_str)
                    if not p.is_file():
                        status.update(f"Storyboard not found: {sb_path_str}")
                        return
                    try:
                        load_storyboard(p)
                    except Exception as exc:
                        status.update(f"Invalid storyboard: {exc}")
                        return
                    app.settings.storyboard_path = p
                elif template_name:
                    tmpl = TemplateMatcher().match(template_name)
                    if tmpl is None:
                        status.update(f"Template '{template_name}' not found.")
                        return
                    app.settings.storyboard_path = None
                    app.settings.prompt = template_name
                    app.settings._template_storyboard = tmpl
                else:
                    app.settings.storyboard_path = None

                self.app.push_screen("settings")

        class SettingsScreen(w["Screen"]):
            BINDINGS = [
                ("alt+left", "back", "Back"),
                ("alt+right", "next", "Next"),
            ]

            def compose(self) -> w["ComposeResult"]:
                yield w["Header"]()
                yield w["Footer"]()
                # Scrollable settings content
                with w["VerticalScroll"](id="settings-scroll"):
                    yield w["Label"]("Settings", classes="title")
                    yield w["Label"]("Output directory:", classes="field-label")
                    yield w["Input"](value=str(settings.output_dir), id="output-dir")
                    yield w["Label"]("Quality:", classes="field-label")
                    yield w["Select"](
                        options=QUALITY_CHOICES, value=DEFAULT_QUALITY, id="quality-select"
                    )
                    yield w["Label"]("Orientation:", classes="field-label")
                    yield w["Select"](
                        options=ORIENTATION_CHOICES,
                        value=DEFAULT_ORIENTATION,
                        id="orientation-select",
                    )
                    yield w["Label"]("Theme:", classes="field-label")
                    yield w["Select"](
                        options=THEME_CHOICES, value=DEFAULT_THEME, id="theme-select"
                    )
                    yield w["Checkbox"](
                        "Burn captions into video", id="captions-check", value=DEFAULT_CAPTIONS
                    )
                    yield w["Checkbox"](
                        "Run frame-lint quality check", id="lint-check", value=DEFAULT_FRAME_LINT
                    )
                # Fixed button row at bottom (never scrolls)
                with w["Horizontal"](id="button-row"):
                    yield w["Button"]("← Back", id="back")
                    yield w["Button"]("Next →", id="next", variant="primary")
                yield w["Static"]("", id="settings-status")

            def on_button_pressed(self, event: w["Button"].Pressed) -> None:
                if event.button.id == "back":
                    self.action_back()
                elif event.button.id == "next":
                    self.action_next()

            def action_back(self) -> None:
                # Don't navigate if the user is typing in an input field
                focused = self.app.focused
                if isinstance(focused, (w["Input"], w["TextArea"])):
                    return
                self.app.pop_screen()

            def action_next(self) -> None:
                # Don't navigate if the user is typing in an input field
                focused = self.app.focused
                if isinstance(focused, (w["Input"], w["TextArea"])):
                    return
                out_input = self.query_one("#output-dir", w["Input"])
                quality_select = self.query_one("#quality-select", w["Select"])
                orientation_select = self.query_one("#orientation-select", w["Select"])
                theme_select = self.query_one("#theme-select", w["Select"])
                captions_check = self.query_one("#captions-check", w["Checkbox"])
                lint_check = self.query_one("#lint-check", w["Checkbox"])

                app = self.app
                app.settings.output_dir = Path(
                    out_input.value.strip() or Path.cwd() / "animatica-output"
                )
                app.settings.quality = (
                    str(quality_select.value) if quality_select.value else DEFAULT_QUALITY
                )
                app.settings.orientation = (
                    str(orientation_select.value)
                    if orientation_select.value
                    else DEFAULT_ORIENTATION
                )
                app.settings.theme = str(theme_select.value) if theme_select.value else DEFAULT_THEME
                app.settings.captions = captions_check.value
                app.settings.frame_lint = lint_check.value

                self.app.push_screen("review")

        class ReviewScreen(w["Screen"]):
            BINDINGS = [
                ("alt+left", "back", "Back"),
                ("alt+right", "next", "Next"),
            ]

            def compose(self) -> w["ComposeResult"]:
                yield w["Header"]()
                yield w["Footer"]()
                with w["VerticalScroll"](id="review-scroll"):
                    yield w["Label"]("Review & Confirm", classes="title")
                    yield w["Static"](id="review-summary")
                    yield w["Static"](id="review-warning", classes="warning")
                # Fixed button row at bottom (never scrolls)
                with w["Horizontal"](id="button-row"):
                    yield w["Button"]("← Back", id="back")
                    yield w["Button"]("Start Render", id="start", variant="primary")
                yield w["Static"]("", id="review-status")

            def on_mount(self) -> None:
                self._refresh_summary()

            def on_button_pressed(self, event: w["Button"].Pressed) -> None:
                if event.button.id == "back":
                    self.action_back()
                elif event.button.id == "start":
                    self.action_next()

            def action_back(self) -> None:
                # Don't navigate if the user is typing in an input field
                focused = self.app.focused
                if isinstance(focused, (w["Input"], w["TextArea"])):
                    return
                self.app.pop_screen()

            def action_next(self) -> None:
                # Don't navigate if the user is typing in an input field
                focused = self.app.focused
                if isinstance(focused, (w["Input"], w["TextArea"])):
                    return
                self.app.push_screen("progress")

            def _refresh_summary(self) -> None:
                s = self.app.settings
                lines = [
                    f"Prompt:        {s.prompt or '(template/storyboard)'}",
                    f"Provider:      {s.provider}",
                    f"Output dir:    {s.output_dir}",
                    f"Quality:       {s.quality}",
                    f"Orientation:   {s.orientation}",
                    f"Theme:         {s.theme}",
                    f"Captions:      {'yes' if s.captions else 'no'}",
                    f"Frame lint:    {'yes' if s.frame_lint else 'no'}",
                ]
                self.query_one("#review-summary", w["Static"]).update("\n".join(lines))

                existing = s.existing_outputs()
                warn = self.query_one("#review-warning", w["Static"])
                if existing:
                    warn.update(
                        "Warning: the following files already exist in the output directory "
                        "and will be overwritten:\n"
                        + "\n".join(f"  - {e}" for e in existing)
                        + "\nChoose a different output directory if you want to keep them."
                    )
                else:
                    warn.update("")

        class ProgressScreen(w["Screen"]):
            BINDINGS = [
                ("escape", "cancel", "Cancel"),
            ]

            def compose(self) -> w["ComposeResult"]:
                yield w["Header"]()
                yield w["Footer"]()
                with w["Vertical"](id="progress-container"):
                    yield w["Label"]("Rendering", classes="title")
                    yield w["Static"]("Starting…", id="progress-stage")
                    yield w["ProgressBar"](id="progress-bar", total=100)
                    yield w["Label"]("Log:", classes="log-label")
                    yield w["TextArea"](id="progress-log", read_only=True)
                    yield w["Button"]("Cancel", id="cancel", variant="error")
                    yield w["Static"]("", id="progress-status")

            def on_mount(self) -> None:
                app = self.app
                app._cancel_event.clear()
                app._render_error = None
                app._result = None

                stage = self.query_one("#progress-stage", w["Static"])
                log = self.query_one("#progress-log", w["TextArea"])
                bar = self.query_one("#progress-bar", w["ProgressBar"])

                stage.update("Validating settings…")
                log.text = "Validating settings...\n"
                bar.progress = 0

                app._render_thread = threading.Thread(target=self._run_render, daemon=True)
                app._render_thread.start()

                app._poll_interval = self.set_interval(0.5, self._poll_render)

            def on_button_pressed(self, event: w["Button"].Pressed) -> None:
                if event.button.id == "cancel":
                    self.action_cancel()

            def action_cancel(self) -> None:
                self._cancel()

            def _run_render(self) -> None:
                app = self.app
                s = app.settings
                try:
                    storyboard_path = s.storyboard_path
                    tmp_sb_path: Path | None = None
                    if s._template_storyboard is not None:
                        tmp_sb_path = (
                            Path(tempfile.mkdtemp(prefix="animatica-tui-")) / "storyboard.json"
                        )
                        dump_storyboard(s._template_storyboard, tmp_sb_path)
                        storyboard_path = tmp_sb_path

                    result = make_video(
                        prompt=s.prompt or None,
                        storyboard_path=storyboard_path,
                        out_dir=s.output_dir,
                        preview=(s.quality == "preview"),
                        quality=s.quality,
                        provider=s.provider,
                        captions=s.captions,
                        frame_lint=s.frame_lint,
                        vertical=s.vertical,
                        theme=s.theme,
                    )
                    if not app._cancel_event.is_set():
                        app._result = result
                except StoryboardGenerationError as exc:
                    if not app._cancel_event.is_set():
                        app._render_error = (
                            "Storyboard generation failed:\n"
                            + "\n".join(f"  - {e}" for e in exc.errors[:6])
                        )
                except (ProviderError, RateLimited) as exc:
                    if not app._cancel_event.is_set():
                        app._render_error = f"Provider error: {exc}"
                except Exception as exc:  # noqa: BLE001
                    if not app._cancel_event.is_set():
                        app._render_error = f"Render failed: {type(exc).__name__}: {exc}"

            def _poll_render(self) -> None:
                app = self.app
                stage = self.query_one("#progress-stage", w["Static"])
                log = self.query_one("#progress-log", w["TextArea"])
                bar = self.query_one("#progress-bar", w["ProgressBar"])
                status = self.query_one("#progress-status", w["Static"])

                if app._render_error:
                    self._stop_poll()
                    stage.update("Error")
                    log.text += f"\n{app._render_error}"
                    status.update("Render failed. Press any key to return.")
                    return

                if app._render_thread is not None and not app._render_thread.is_alive():
                    self._stop_poll()
                    if app._cancel_event.is_set():
                        stage.update("Cancelled")
                        status.update("Render stopped. Press any key to return.")
                    elif app._result is not None:
                        stage.update("Complete")
                        bar.progress = 100
                        log.text += (
                            f"\nRender complete!\n"
                            f"Video: {app._result.video}\n"
                            f"Report: {app._result.report}\n"
                        )
                        self.app.push_screen("result")
                    return

                stage.update("Rendering video…")
                bar.progress = min(bar.progress + 5, 90)

            def _stop_poll(self) -> None:
                app = self.app
                if app._poll_interval is not None:
                    app._poll_interval.stop()
                    app._poll_interval = None

            def _cancel(self) -> None:
                app = self.app
                app._cancel_event.set()
                btn = self.query_one("#cancel", w["Button"])
                btn.disabled = True
                stage = self.query_one("#progress-stage", w["Static"])
                status = self.query_one("#progress-status", w["Static"])
                stage.update("Cancelling…")
                status.update("Waiting for render to stop...")

                if app._render_thread is not None:
                    app._render_thread.join(timeout=15)

                self._stop_poll()
                stage.update("Cancelled")
                status.update("Render stopped. Press any key to return.")

        class ResultScreen(w["Screen"]):
            BINDINGS = [
                ("alt+n", "new_job", "New Job"),
                ("f10", "quit", "Quit"),
            ]

            def compose(self) -> w["ComposeResult"]:
                yield w["Header"]()
                yield w["Footer"]()
                with w["Vertical"](id="result-container"):
                    yield w["Label"]("Render Complete", classes="title")
                    yield w["Static"](id="result-paths")
                    yield w["Button"]("Open video", id="open-video")
                    yield w["Button"]("Start Another Job", id="new-job")
                    yield w["Button"]("Done", id="done", variant="primary")
                    yield w["Static"]("", id="result-status")

            def on_mount(self) -> None:
                r = self.app._result  # type: ignore[attr-defined]
                if r is not None:
                    paths = [
                        f"Video:    {r.video}",
                        f"Storyboard: {r.storyboard}",
                        f"Report:   {r.report}",
                        f"Captions: {r.captions}",
                    ]
                    if r.warnings:
                        paths.append("")
                        paths.append("Warnings:")
                        for wmsg in r.warnings:
                            paths.append(f"  - {wmsg}")
                    self.query_one("#result-paths", w["Static"]).update("\n".join(paths))

            def on_button_pressed(self, event: w["Button"].Pressed) -> None:
                if event.button.id == "open-video":
                    self._open_video()
                elif event.button.id == "new-job":
                    self.action_new_job()
                elif event.button.id == "done":
                    self.action_quit()

            def action_new_job(self) -> None:
                # Return to Welcome screen to start a new job.
                # Pop screens until we reach Welcome, but never pop the last
                # screen (that would raise ScreenStackError).
                while len(self.app._screen_stack) > 1:
                    cls_name = self.screen.__class__.__name__
                    if cls_name == "WelcomeScreen":
                        break
                    self.app.pop_screen()

            def action_quit(self) -> None:
                self.app.exit()

            def _open_video(self) -> None:
                r = self.app._result  # type: ignore[attr-defined]
                status = self.query_one("#result-status", w["Static"])
                if r is None or not r.video.is_file():
                    status.update("Video file not found.")
                    return
                try:
                    if sys.platform == "win32":
                        os.startfile(str(r.video))  # type: ignore[attr-defined]
                    elif sys.platform == "darwin":
                        subprocess.run(["open", str(r.video)], check=False)
                    else:
                        subprocess.run(["xdg-open", str(r.video)], check=False)
                    status.update("Opening video…")
                except Exception as exc:  # noqa: BLE001
                    status.update(f"Could not open video: {exc}\nPath: {r.video}")

        return {
            "welcome": WelcomeScreen,
            "settings": SettingsScreen,
            "review": ReviewScreen,
            "progress": ProgressScreen,
            "result": ResultScreen,
        }

    # -- run ----------------------------------------------------------------

    def create_app(self):
        """Create and return a configured Textual App instance.

        Tests can call this directly and use ``app.run_test()`` for
        headless pilot testing.
        """
        w = self.w
        screens = self._screens
        settings = self.settings
        cancel_event = self._cancel_event

        class AnimaticaApp(w["App"]):
            TITLE = "Animatica TUI"

            def __init__(self):
                super().__init__()
                self.settings = settings
                self._cancel_event = cancel_event
                self._result = None
                self._render_thread = None
                self._render_error = None
                self._poll_interval = None
                # Install screens dynamically so run_test() can find them
                for name, screen_cls in screens.items():
                    self.install_screen(screen_cls, name)

            def compose(self) -> w["ComposeResult"]:  # type: ignore[attr-defined]
                yield w["Header"]()
                yield w["Footer"]()

            def on_mount(self) -> None:
                self.push_screen("welcome")

            def action_back(self) -> None:
                # Navigate back based on current screen
                screen_id = self.screen.id if hasattr(self.screen, "id") else None
                # Textual screens don't have stable ids; check screen class name
                cls_name = self.screen.__class__.__name__
                if cls_name == "SettingsScreen":
                    self.pop_screen()
                elif cls_name == "ReviewScreen":
                    self.pop_screen()
                elif cls_name == "WelcomeScreen":
                    pass  # nothing to go back to
                elif cls_name == "ProgressScreen":
                    pass  # can't go back during render
                elif cls_name == "ResultScreen":
                    self.exit()

            def action_next(self) -> None:
                cls_name = self.screen.__class__.__name__
                if cls_name == "WelcomeScreen":
                    self.screen.action_next()
                elif cls_name == "SettingsScreen":
                    self.screen.action_next()
                elif cls_name == "ReviewScreen":
                    self.screen.action_next()

            def action_cancel(self) -> None:
                cls_name = self.screen.__class__.__name__
                if cls_name == "ProgressScreen":
                    self.screen.action_cancel()

            def action_quit(self) -> None:
                cls_name = self.screen.__class__.__name__
                if cls_name == "ResultScreen":
                    self.exit()
                else:
                    self.exit()

        return AnimaticaApp()

    def run(self) -> None:
        """Start the Textual application."""
        self.create_app().run()


def run_tui() -> None:
    """Public entry point: launch the Animatica TUI.

    Raises a clear error if ``textual`` is not installed.
    """
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "The 'tui' command requires the optional 'textual' package. "
            "Install it with:  pip install 'animatica[tui]'"
        ) from exc
    app = AnimaticaTuiApp()
    app.run()

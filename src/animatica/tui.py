"""Animatica Terminal User Interface.

A guided, keyboard-first studio for turning a prompt into an explainer video.
It reuses :func:`animatica.pipeline.make_video` rather than duplicating the
pipeline, and it never renders anything itself.

Layout (one screen, three steps, persistent sidebar):

    ┌ topbar: brand · current step · provider ───────────────────────────┐
    │ 1 Prompt │ 2 Storyboard │ 3 Render              │ Job             │
    │                                                  │ source          │
    │   (the active step)                              │ output dir      │
    │                                                  │ quality/theme   │
    │                                                  │ captions/lint   │
    ├──────────────────────────────────────────────────┴─────────────────┤
    │ status line                                                        │
    └────────────────────────────────────────────────────────────────────┘

Requires the optional ``textual`` package::

    pip install "animatica[tui]"

The module imports cleanly without textual: the import happens inside
:func:`run_tui` / :meth:`AnimaticaTuiApp.create_app`, so ``animatica --help``
and the rest of the CLI keep working in a minimal install.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from animatica.ai.base import ProviderError, RateLimited, StoryboardGenerationError
from animatica.ai.template import TemplateMatcher
from animatica.components.registry import default_registry
from animatica.pipeline import MakeResult, make_video
from animatica.storyboard.models import Storyboard, dump_storyboard, load_storyboard


# ---------------------------------------------------------------------------
# Lazy import of Textual
# ---------------------------------------------------------------------------


def _import_textual() -> dict[str, Any]:
    """Import the Textual names this app uses, with a helpful error if missing."""
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
        from textual.screen import ModalScreen
        from textual.widgets import (
            Button,
            Collapsible,
            ContentSwitcher,
            DataTable,
            Footer,
            Input,
            ProgressBar,
            RichLog,
            Select,
            Static,
            Switch,
            TextArea,
        )
        from textual import work

        from animatica.tui_picker import FilterSelect
    except ImportError as exc:
        raise ImportError(
            "The 'tui' command requires the optional 'textual' package. "
            "Install it with:  pip install 'animatica[tui]'  "
            f"(import failed: {exc})"
        ) from exc

    return {
        "App": App,
        "Binding": Binding,
        "Button": Button,
        "Collapsible": Collapsible,
        "ComposeResult": ComposeResult,
        "ContentSwitcher": ContentSwitcher,
        "DataTable": DataTable,
        "Footer": Footer,
        "Grid": Grid,
        "Horizontal": Horizontal,
        "Input": Input,
        "ModalScreen": ModalScreen,
        "ProgressBar": ProgressBar,
        "RichLog": RichLog,
        "FilterSelect": FilterSelect,
        "Select": Select,
        "Static": Static,
        "Switch": Switch,
        "TextArea": TextArea,
        "Vertical": Vertical,
        "VerticalScroll": VerticalScroll,
        "work": work,
    }


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_QUALITY = "preview"
DEFAULT_ORIENTATION = "landscape"
DEFAULT_THEME = "dark-blue"
DEFAULT_PROVIDER = "template"  # offline by default: no API key needed
DEFAULT_FRAME_LINT = False
DEFAULT_CAPTIONS = True

#: Labels are kept short enough to fit a Select in a half-width column of an
#: 80-column terminal (the smallest size the TUI promises to support).
QUALITY_CHOICES = [
    ("Preview 480p", "preview"),
    ("Standard 720p", "standard"),
    ("High 1080p", "high"),
]
ORIENTATION_CHOICES = [
    ("Landscape 16:9", "landscape"),
    ("Portrait 9:16", "portrait"),
]
THEME_CHOICES = [
    ("Dark Blue", "dark-blue"),
    ("Light", "light"),
    ("High Contrast", "high-contrast"),
]
PROVIDER_CHOICES = [
    ("Template", "template"),
    ("NVIDIA NIM", "nim"),
    ("Groq", "groq"),
    ("OpenRouter", "openrouter"),
    ("Ollama", "ollama"),
]

# Default output location: a dedicated folder in the user's home directory,
# never the current working directory (which might be Downloads).
DEFAULT_OUTPUT_DIR = Path.home() / "animatica-output"


def _path_from_input(value: str | Path | None, default: Path | None = None) -> Path | None:
    """Parse a pasted path, accepting the surrounding quotes Explorer often adds."""
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    return Path(text).expanduser() if text else default


STEPS = ("prompt", "storyboard", "job", "render")


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

APP_CSS = """
Screen {
    background: #101116;
    color: #f2f2f4;
}

/* Quiet chrome; one accent, clear hierarchy, no dashboard clutter. */
#topbar {
    height: 3;
    padding: 1 2 0 2;
    background: #15161c;
    border-bottom: solid #292a33;
}
#topbar .brand {
    width: auto;
    text-style: bold;
    color: #d8f99f;
    margin-right: 2;
}
#topbar .tagline {
    width: 1fr;
    color: #9a9ba5;
}
#topbar .step {
    width: auto;
    color: #d8f99f;
    margin-right: 2;
}
#topbar-help { min-width: 8; margin-right: 0; }

ContentSwitcher { height: 1fr; }
VerticalScroll {
    height: 1fr;
    padding: 1 2;
    scrollbar-gutter: stable;
}

#step-nav {
    height: 4;
    padding: 0 2;
    border-top: solid #292a33;
    background: #15161c;
    align-vertical: middle;
}
#nav-note { width: 1fr; color: #8e909a; }
#back, #next { min-width: 16; }

.pane-title {
    margin-top: 1;
    text-style: bold;
    color: #f2f2f4;
}
.pane-subtitle { color: #a0a1aa; margin-bottom: 0; }
.hint { color: #858792; }
.field-label { color: #b8b9c2; margin-top: 1; }
.row { height: auto; margin-top: 1; }

Input, TextArea { border: round #373943; background: #17181f; }
SelectCurrent { border: round #373943; background: #17181f; }
Input:focus, TextArea:focus { border: round #d8f99f; }
Select:focus > SelectCurrent { border: round #d8f99f; }
SelectOverlay { border: round #373943; }
Button { margin-right: 1; min-width: 14; }
Button:focus { border: round #d8f99f; }
Button.-primary { background: #d8f99f; color: #171a0e; text-style: bold; }
Button.-error { background: #f2a896; color: #24140f; }

/* Basic job choices stay visible; infrequent controls are progressive. */
#job-grid, #advanced-job-grid {
    grid-size: 2;
    grid-columns: 17 1fr;
    grid-gutter: 0 1;
    height: auto;
}
#job-grid .field-label, #advanced-job-grid .field-label {
    color: #b8b9c2;
    height: 3;
    content-align: left middle;
}
#job-grid Input, #job-grid Select, #job-grid FilterSelect,
#advanced-job-grid Input, #advanced-job-grid Select, #advanced-job-grid FilterSelect { width: 1fr; }
#job-grid FilterSelect, #advanced-job-grid FilterSelect { height: auto; }
#job-grid FilterSelect #fs-list, #advanced-job-grid FilterSelect #fs-list { background: #202126; }
#job-grid Switch, #advanced-job-grid Switch { height: 3; }
#job-advanced, #storyboard-advanced, #render-details { margin-top: 1; }
.warn { color: #f2a896; margin-top: 1; }
.side-value { color: #d1d1d7; }
.side-head { height: 1; margin-top: 0; }

/* Storyboard preview is primary; raw JSON is an opt-in advanced tool. */
#storyboard-details { height: auto; }
#storyboard-table { min-height: 5; border: round #373943; }
#storyboard-json { height: 8; min-height: 5; }

/* Keep render status obvious; technical detail is available on demand. */
#render-stage { color: #d1d1d7; }
#progress-bar { margin: 1 0; }
#render-log {
    height: 1fr;
    min-height: 6;
    border: round #373943;
    background: #15161c;
    padding: 0 1;
}
#render-summary { color: #d1d1d7; margin-top: 1; }

#status {
    height: 1;
    padding: 0 2;
    background: #1a1b22;
    color: #b4b5bd;
}
#status.ok { color: #d8f99f; }
#status.error { color: #f2a896; }
#status.busy { color: #f1ca7d; }

HelpScreen { align: center middle; background: #000000; }
#help-card {
    width: 72;
    height: auto;
    max-height: 90%;
    padding: 1 2;
    border: round #45464f;
    background: #191a21;
}
#help-card .pane-title { margin-top: 0; }
"""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _saved_defaults() -> dict[str, Any]:
    """Defaults remembered from the previous session, validated against the menus.

    Reading config is a convenience: if it is missing or corrupt the studio simply
    starts from the built-in defaults.
    """
    try:
        from animatica.config import load_config

        cfg = load_config()
    except Exception:
        return {}
    known = {
        "quality": {value for _, value in QUALITY_CHOICES},
        "theme": {value for _, value in THEME_CHOICES},
        "orientation": {value for _, value in ORIENTATION_CHOICES},
    }
    out: dict[str, Any] = {}
    for key, allowed in known.items():
        candidate = getattr(cfg, key, None)
        if isinstance(candidate, str) and candidate in allowed:
            out[key] = candidate
    for key in ("captions", "frame_lint"):
        candidate = getattr(cfg, key, None)
        if isinstance(candidate, bool):
            out[key] = candidate
    return out


def _persist_defaults(settings: "TuiSettings") -> None:
    """Write the current job-step choices back to the config file."""
    try:
        from animatica.config import load_config, save_config

        cfg = load_config()
        cfg.quality = settings.quality
        cfg.theme = settings.theme
        cfg.orientation = settings.orientation
        cfg.captions = settings.captions
        cfg.frame_lint = settings.frame_lint
        save_config(cfg)
    except Exception:
        pass  # remembering defaults is never worth breaking a render for


class TuiSettings:
    """Mutable settings collected by the studio."""

    def __init__(self) -> None:
        defaults = _saved_defaults()
        self.prompt: str = ""
        self.storyboard_path: Path | None = None
        self.provider: str = DEFAULT_PROVIDER
        self.model: str | None = None
        self.output_dir: Path = DEFAULT_OUTPUT_DIR
        self.quality: str = defaults.get("quality", DEFAULT_QUALITY)
        self.orientation: str = defaults.get("orientation", DEFAULT_ORIENTATION)
        self.theme: str = defaults.get("theme", DEFAULT_THEME)
        self.frame_lint: bool = defaults.get("frame_lint", DEFAULT_FRAME_LINT)
        self.captions: bool = defaults.get("captions", DEFAULT_CAPTIONS)

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
# The app
# ---------------------------------------------------------------------------


class AnimaticaTuiApp:
    """Builds and runs the Textual application (lazily, so imports stay cheap)."""

    def __init__(self) -> None:
        self.w = _import_textual()
        self.settings = TuiSettings()
        self._app: Any = None

    # -- construction ------------------------------------------------------

    def create_app(self):
        """Create and return the Textual App. Tests drive this with run_test()."""
        w = self.w
        settings = self.settings
        wrapper = self

        class HelpScreen(w["ModalScreen"]):
            BINDINGS = [
                w["Binding"]("escape", "close", "Close", show=False),
                w["Binding"]("f1", "close", "Close", show=False),
            ]

            def compose(self) -> w["ComposeResult"]:  # type: ignore[valid-type]
                with w["Vertical"](id="help-card"):
                    yield w["Static"]("A simple four-step flow", classes="pane-title")
                    yield w["Static"](
                        "1  Idea     Describe a topic, pick a starter, or open a storyboard.\n"
                        "2  Scenes   Preview a starter or file; prompt scenes are created at "
                        "render.\n"
                        "3  Style    Keep the recommended settings or adjust the options.\n"
                        "4  Render   Create the video and open it when it is ready.\n\n"
                        "Tab moves between controls. Enter selects. F1 or Escape closes help.\n"
                        "Ctrl+J continues; Ctrl+B goes back; Ctrl+R starts a render.\n"
                        "Ctrl+Shift+C copies render details.",
                        id="help-copy",
                    )
                    with w["Horizontal"](classes="row"):
                        yield w["Button"]("Close", id="close-help", variant="primary")

            def on_button_pressed(self, event: Any) -> None:
                if getattr(event.button, "id", "") == "close-help":
                    self.dismiss()

            def action_close(self) -> None:
                self.dismiss()

        class StudioApp(w["App"]):
            CSS = APP_CSS
            TITLE = "Animatica"
            BINDINGS = [
                w["Binding"]("ctrl+j", "next_step", "Continue"),
                w["Binding"]("ctrl+b", "prev_step", "Back"),
                w["Binding"]("ctrl+r", "start_render", "Render"),
                w["Binding"]("ctrl+shift+c", "copy_render_log", "Copy details", show=False),
                w["Binding"]("f1", "help", "Help"),
                w["Binding"]("ctrl+q", "quit", "Quit"),
            ]

            def __init__(self) -> None:
                super().__init__()
                self.settings = settings
                self.storyboard: Storyboard | None = None
                self.source_label = "—"
                self.result: MakeResult | None = None
                self.busy = False
                self.started_at = 0.0
                self.cancel_event = threading.Event()
                self._timer: Any = None
                self._render_log_lines: list[str] = []

            # -- layout ----------------------------------------------------

            def compose(self) -> w["ComposeResult"]:  # type: ignore[valid-type]
                with w["Horizontal"](id="topbar"):
                    yield w["Static"]("ANIMATICA", classes="brand")
                    yield w["Static"](
                        "Create a video from an idea",
                        id="tagline",
                        classes="tagline",
                    )
                    yield w["Static"]("", id="topbar-step", classes="step")
                    yield w["Button"]("Help · F1", id="topbar-help")

                with w["ContentSwitcher"](initial="pane-prompt", id="steps"):
                    with w["VerticalScroll"](id="pane-prompt"):
                        yield from self._compose_prompt()
                    with w["VerticalScroll"](id="pane-storyboard"):
                        yield from self._compose_storyboard()
                    with w["VerticalScroll"](id="pane-job"):
                        yield from self._compose_job()
                    with w["VerticalScroll"](id="pane-render"):
                        yield from self._compose_render()

                with w["Horizontal"](id="step-nav"):
                    yield w["Button"]("← Back", id="back", disabled=True)
                    yield w["Static"]("", id="nav-note")
                    yield w["Button"]("Continue →", id="next", variant="primary")

                yield w["Static"]("Ready. Choose how to start.", id="status")
                yield w["Footer"]()

            def _compose_prompt(self):
                yield w["Static"]("Start with an idea", classes="pane-title")
                yield w["Static"](
                    "Describe a topic, choose a starter, or open a storyboard.",
                    classes="pane-subtitle",
                )
                yield w["Static"]("How would you like to begin?", classes="field-label")
                yield w["Select"](
                    options=[
                        ("Describe a topic", "prompt"),
                        ("Choose a starter", "template"),
                        ("Open a storyboard file", "storyboard"),
                    ],
                    value="prompt",
                    allow_blank=False,
                    id="source-mode",
                )
                yield w["Input"](
                    placeholder="e.g. Why do leaves change color?",
                    id="prompt-input",
                )
                template_options = [(name, name) for name, _ in TemplateMatcher().list_templates()]
                yield w["Select"](
                    options=template_options,
                    allow_blank=True,
                    prompt="Choose an offline starter",
                    id="template-select",
                )
                yield w["Input"](
                    placeholder="Path to storyboard.json",
                    id="sb-path-input",
                )
                yield w["Static"](
                    "Scenes from an idea are drafted when you create the video.",
                    id="source-hint",
                    classes="hint",
                )
                with w["Horizontal"](classes="row"):
                    yield w["Button"]("Clear", id="clear")
                yield w["Static"]("", id="prompt-status", classes="hint")

            def _compose_storyboard(self):
                yield w["Static"]("Your scene plan", classes="pane-title")
                yield w["Static"](
                    "Review the flow before creating your video.",
                    classes="pane-subtitle",
                )
                yield w["Static"](
                    "Your scene plan will be drafted when you create the video.\n"
                    "There is nothing to review yet; you can continue to choose a style.",
                    id="storyboard-empty",
                    classes="hint",
                )
                with w["Vertical"](id="storyboard-details"):
                    with w["Horizontal"](classes="side-head"):
                        yield w["Static"]("", id="storyboard-summary", classes="side-value")
                    yield w["DataTable"](id="storyboard-table", zebra_stripes=True)
                    with w["Collapsible"](
                        title="Advanced · raw storyboard JSON",
                        collapsed=True,
                        id="storyboard-advanced",
                    ):
                        yield w["Static"](
                            "Edit only if you are comfortable with the storyboard format.",
                            classes="hint",
                        )
                        with w["Horizontal"](classes="row"):
                            yield w["Button"]("Validate edits", id="validate")
                            yield w["Button"]("Reload", id="reload")
                        yield w["TextArea"](id="storyboard-json", language="json")
                yield w["Static"]("", id="storyboard-status", classes="hint")

            def _compose_job(self):
                yield w["Static"]("Choose a style", classes="pane-title")
                yield w["Static"](
                    "The recommended settings are ready to use. Change only what you need.",
                    classes="pane-subtitle",
                )
                yield w["Static"]("Source: —", id="side-source", classes="side-value")
                yield w["Static"]("", id="output-summary", classes="hint")
                yield w["Static"]("", id="overwrite-warning", classes="warn")

                with w["Grid"](id="job-grid"):
                    yield w["Static"]("Quality", classes="field-label")
                    yield w["FilterSelect"](
                        options=QUALITY_CHOICES,
                        value=self.settings.quality,
                        id="quality-select",
                    )
                    yield w["Static"]("Format", classes="field-label")
                    yield w["FilterSelect"](
                        options=ORIENTATION_CHOICES,
                        value=self.settings.orientation,
                        id="orientation-select",
                    )

                with w["Collapsible"](
                    title="More options",
                    collapsed=True,
                    id="job-advanced",
                ):
                    with w["Grid"](id="advanced-job-grid"):
                        yield w["Static"]("Provider", classes="field-label")
                        yield w["FilterSelect"](
                            options=PROVIDER_CHOICES,
                            value=self.settings.provider,
                            id="provider-select",
                        )
                        yield w["Static"]("Theme", classes="field-label")
                        yield w["FilterSelect"](
                            options=THEME_CHOICES,
                            value=self.settings.theme,
                            id="theme-select",
                        )
                        yield w["Static"]("Burn captions", classes="field-label")
                        yield w["Switch"](value=self.settings.captions, id="captions-switch")
                        yield w["Static"]("Frame lint", classes="field-label")
                        yield w["Switch"](value=self.settings.frame_lint, id="frame-lint-switch")
                        yield w["Static"]("Output folder", classes="field-label")
                        yield w["Input"](value=str(self.settings.output_dir), id="output-dir")
                    yield w["Static"](
                        "Template runs offline. Other providers may need an API key.",
                        id="provider-hint",
                        classes="hint",
                    )

            def _compose_render(self):
                yield w["Static"]("Create your video", classes="pane-title")
                yield w["Static"](
                    "Rendering can take a few minutes. Progress and errors will appear here.",
                    classes="pane-subtitle",
                )
                yield w["Static"]("Ready to start.", id="render-stage")
                yield w["ProgressBar"](id="progress-bar", total=None, show_eta=False)
                with w["Horizontal"](classes="row"):
                    yield w["Button"]("Create video", id="start", variant="primary")
                    yield w["Button"]("Cancel", id="cancel", variant="error", disabled=True)
                    yield w["Button"]("Open video", id="open-video", disabled=True)
                    yield w["Button"]("Copy details", id="copy-render-log", disabled=True)
                yield w["Static"]("", id="render-summary")
                with w["Collapsible"](
                    title="Render details",
                    collapsed=True,
                    id="render-details",
                ):
                    yield w["RichLog"](id="render-log", markup=True, wrap=True)

            def on_mount(self) -> None:
                self._layout_storyboard()
                self._q("#tagline", w["Static"]).display = self.size.width >= 96
                self._apply_source_mode("prompt")
                self._q("#storyboard-details").display = False
                self._refresh_job_summary()
                self._goto("prompt")
                self._set_status("Ready. Choose how to start.")

            # -- small helpers --------------------------------------------

            def _q(self, selector: str, *types: Any) -> Any:
                return self.query_one(selector, *types)

            def _set_status(self, message: str, kind: str = "") -> None:
                status = self._q("#status", w["Static"])
                status.update(message)
                status.classes = kind

            def _set_pane_status(self, widget_id: str, message: str) -> None:
                self._q(f"#{widget_id}", w["Static"]).update(message)

            def _append_render_log(self, text: str, style: str | None = None) -> None:
                """Keep a plain-text copy for clipboard while rendering safe Rich markup."""
                from rich.markup import escape

                plain = str(text)
                self._render_log_lines.append(plain)
                escaped = escape(plain)
                rendered = f"[{style}]{escaped}[/{style}]" if style else escaped
                self._q("#render-log", w["RichLog"]).write(rendered)
                self._q("#copy-render-log", w["Button"]).disabled = False

            def _copy_render_log(self) -> None:
                if not self._render_log_lines:
                    self._set_status("No render details to copy yet.", "busy")
                    return
                try:
                    self.copy_to_clipboard("\n".join(self._render_log_lines))
                except Exception as exc:  # noqa: BLE001 - clipboard support is terminal-dependent
                    self._set_status(f"Could not copy render details: {exc}", "error")
                    return
                self._set_status("Render details copied. Paste with Ctrl+V.", "ok")

            def _apply_source_mode(self, mode: str) -> None:
                visible = {
                    "prompt": "#prompt-input",
                    "template": "#template-select",
                    "storyboard": "#sb-path-input",
                }
                for selector in visible.values():
                    self._q(selector).display = selector == visible.get(mode)
                hints = {
                    "prompt": (
                        "We will try an offline match. Use an AI provider in More options "
                        "for a custom explanation."
                    ),
                    "template": (
                        "Pick a ready-made example. Templates work offline and need no API key."
                    ),
                    "storyboard": "Choose a storyboard JSON file you already have.",
                }
                self._q("#source-hint", w["Static"]).update(hints.get(mode, ""))

            def _goto(self, step: str) -> None:
                if step not in STEPS:
                    return
                self._q("#steps", w["ContentSwitcher"]).current = f"pane-{step}"
                self._q("#next", w["Button"]).display = step != "render"
                self._q("#back", w["Button"]).disabled = step == "prompt" or self.busy
                index = STEPS.index(step) + 1
                label = {
                    "prompt": "Idea",
                    "storyboard": "Scenes",
                    "job": "Style",
                    "render": "Render",
                }[step]
                self._q("#nav-note", w["Static"]).update(f"{index} of 4  ·  {label}")
                self.call_after_refresh(self._focus, step)
                self._update_topbar()

            def on_resize(self, event: Any) -> None:
                # Keep the header calm at the supported 80-column size.
                self._q("#tagline", w["Static"]).display = event.size.width >= 96
                self._layout_storyboard()

            #: topbar 3, navigation 4 (including its border), status 1 and footer 1
            _CHROME_ROWS = 9

            def _layout_storyboard(self) -> None:
                """Keep the scene preview and optional JSON editor usable at 80x24."""
                try:
                    pane_rows = max(8, self.size.height - self._CHROME_ROWS)
                    table_rows = max(5, min(12, pane_rows - 8))
                    self._q("#storyboard-table", w["DataTable"]).styles.height = table_rows
                    self._q("#storyboard-json", w["TextArea"]).styles.height = max(6, pane_rows - 8)
                except Exception:
                    pass

            def _focus(self, step: str) -> None:
                if step == "prompt":
                    mode = str(self._q("#source-mode", w["Select"]).value or "prompt")
                    selector = {
                        "prompt": "#prompt-input",
                        "template": "#template-select",
                        "storyboard": "#sb-path-input",
                    }.get(mode, "#source-mode")
                else:
                    selector = {
                        "storyboard": "#next",
                        "job": "#output-dir",
                        "render": "#start",
                    }[step]
                try:
                    self._q(selector).focus()
                except Exception:  # hidden or disabled focus targets are not fatal
                    pass
                try:
                    self._q(f"#pane-{step}").scroll_home(animate=False)
                except Exception:
                    pass

            def _current_step(self) -> str:
                current = self._q("#steps", w["ContentSwitcher"]).current or "pane-prompt"
                return current.replace("pane-", "")

            def _update_topbar(self) -> None:
                step = self._current_step()
                index = STEPS.index(step) + 1 if step in STEPS else 0
                label = {
                    "prompt": "IDEA",
                    "storyboard": "SCENES",
                    "job": "STYLE",
                    "render": "RENDER",
                }.get(step, "")
                self._q("#topbar-step", w["Static"]).update(f"{index:02d} / 04  ·  {label}")

            # -- settings sync --------------------------------------------

            def _sync_settings(self) -> None:
                s = self.settings
                # The selected source mode is explicit: hidden alternate inputs
                # never compete with the source the user chose.
                source_mode = str(self._q("#source-mode", w["Select"]).value or "prompt")
                s.prompt = (
                    self._q("#prompt-input", w["Input"]).value.strip()
                    if source_mode == "prompt"
                    else ""
                )
                path_value = self._q("#sb-path-input", w["Input"]).value.strip()
                s.storyboard_path = (
                    _path_from_input(path_value)
                    if source_mode == "storyboard" and path_value
                    else None
                )
                output_dir = _path_from_input(
                    self._q("#output-dir", w["Input"]).value, DEFAULT_OUTPUT_DIR
                )
                assert output_dir is not None
                s.output_dir = output_dir
                s.quality = str(
                    self._q("#quality-select", w["FilterSelect"]).value or DEFAULT_QUALITY
                )
                s.theme = str(
                    self._q("#theme-select", w["FilterSelect"]).value or DEFAULT_THEME
                )
                s.orientation = str(
                    self._q("#orientation-select", w["FilterSelect"]).value or DEFAULT_ORIENTATION
                )
                s.provider = str(
                    self._q("#provider-select", w["FilterSelect"]).value or DEFAULT_PROVIDER
                )
                s.captions = bool(self._q("#captions-switch", w["Switch"]).value)
                s.frame_lint = bool(self._q("#frame-lint-switch", w["Switch"]).value)

            def _save_defaults(self) -> None:
                _persist_defaults(self.settings)

            def _refresh_job_summary(self) -> None:
                self._sync_settings()
                self._q("#side-source", w["Static"]).update(f"Source: {self.source_label}")
                self._q("#output-summary", w["Static"]).update(
                    f"Saving to {self.settings.output_dir} · change under More options"
                )
                self._update_topbar()
                existing = self.settings.existing_outputs()
                warning = self._q("#overwrite-warning", w["Static"])
                warning.update(f"Will overwrite: {', '.join(existing)}" if existing else "")
                warning.display = bool(existing)
                self._refresh_duration()

            def _refresh_duration(self) -> None:
                summary = self._q("#storyboard-summary", w["Static"])
                if self.storyboard is None:
                    summary.update("")
                    return
                registry = default_registry()
                total = 0.0
                for scene in self.storyboard.scenes:
                    for beat in scene.beats:
                        try:
                            component = registry.get(beat.component)
                            total += component.duration(
                                component.Params.model_validate(beat.params)
                            )
                        except Exception:  # unknown/invalid component: leave it out
                            continue
                duration = f"about {total:.0f}s" if total else "duration varies"
                summary.update(
                    f"{self.storyboard.title}  ·  {len(self.storyboard.scenes)} scenes  · "
                    f"{duration}"
                )

            # -- storyboard plumbing --------------------------------------

            def _show_storyboard(self, storyboard: Storyboard, source: str) -> None:
                self.storyboard = storyboard
                self.source_label = source
                self._q("#storyboard-empty", w["Static"]).display = False
                self._q("#storyboard-details").display = True
                self._q("#side-source", w["Static"]).update(f"Source: {source}")

                self._refresh_table()
                self._q("#storyboard-json", w["TextArea"]).text = storyboard.model_dump_json(
                    indent=2
                )
                self._refresh_duration()
                self._set_status(f"Loaded {source}: {len(storyboard.scenes)} scene(s).", "ok")

            def _beat_preview(self, beat: Any) -> str:
                """Turn internal component params into a compact, human label."""
                params = beat.params
                detail: Any = (
                    params.get("title")
                    or params.get("label")
                    or params.get("fn")
                    or params.get("text")
                )
                if detail is None and params.get("latex"):
                    detail = (
                        params["latex"][0]
                        if isinstance(params["latex"], list)
                        else params["latex"]
                    )
                if detail is None and params.get("items"):
                    items = params["items"]
                    if isinstance(items, (list, tuple)):
                        detail = ", ".join(str(item) for item in items[:3])
                        if len(items) > 3:
                            detail += ", …"
                    else:
                        detail = str(items)
                if detail is None and params.get("labels"):
                    labels = params["labels"]
                    if isinstance(labels, (list, tuple)):
                        detail = ", ".join(str(item) for item in labels[:3])
                        if len(labels) > 3:
                            detail += ", …"
                    else:
                        detail = str(labels)
                visual = beat.component.replace("_", " ").title()
                if detail not in (None, ""):
                    visual += f" · {detail}"
                return visual

            def _refresh_table(self) -> None:
                assert self.storyboard is not None
                table = self._q("#storyboard-table", w["DataTable"])
                # The user-facing columns describe the visual and narration;
                # implementation params stay in the Advanced JSON disclosure.
                if not table.columns:
                    table.add_columns("Scene", "Visual", "Narration")
                table.clear(columns=False)
                for si, scene in enumerate(self.storyboard.scenes, 1):
                    for beat in scene.beats:
                        table.add_row(
                            f"Scene {si}",
                            self._beat_preview(beat),
                            beat.caption or "—",
                        )
                if table.row_count:
                    table.move_cursor(row=0, column=0)
                table.scroll_home(animate=False)

            def _advance_from_prompt(self) -> None:
                mode = str(self._q("#source-mode", w["Select"]).value or "prompt")
                self._sync_settings()
                self._set_pane_status("prompt-status", "")

                if mode == "prompt":
                    prompt = self.settings.prompt
                    if not prompt:
                        self._set_pane_status("prompt-status", "Write a topic to continue.")
                        self._set_status("Add an idea first.", "error")
                        return
                    # The generated storyboard appears during render. Keep this
                    # step honest rather than showing a fake or stale preview.
                    self.storyboard = None
                    self.source_label = "prompt"
                    self._q("#side-source", w["Static"]).update("Source: prompt")
                    self._q("#storyboard-empty", w["Static"]).display = True
                    self._q("#storyboard-details").display = False
                    self._refresh_duration()
                    self._set_status("Idea saved. Continue to choose a style.", "ok")
                    self._goto("storyboard")
                    return

                if mode == "template":
                    template_value = self._q("#template-select", w["Select"]).value
                    template_name = (
                        str(template_value)
                        if template_value not in (None, w["Select"].NULL, "")
                        else None
                    )
                    if template_name is None:
                        self._set_pane_status("prompt-status", "Choose a starter to continue.")
                        self._set_status("Choose a starter first.", "error")
                        return
                    storyboard = TemplateMatcher().by_name(template_name)
                    if storyboard is None:
                        self._set_pane_status(
                            "prompt-status", f"Starter {template_name!r} not found."
                        )
                        self._set_status("That starter is no longer available.", "error")
                        return
                    self.settings.prompt = ""
                    self.settings.storyboard_path = None
                    self._show_storyboard(storyboard, f"template: {template_name}")
                    self._goto("storyboard")
                    return

                if mode == "storyboard":
                    path_input = self._q("#sb-path-input", w["Input"])
                    sb_path_text = path_input.value.strip()
                    path = _path_from_input(sb_path_text)
                    if path is None:
                        self._set_pane_status("prompt-status", "Enter the storyboard file path.")
                        self._set_status("Choose a storyboard file first.", "error")
                        return
                    if not path.is_file():
                        self._set_pane_status("prompt-status", f"Not found: {path}")
                        self._set_status("Storyboard file not found.", "error")
                        return
                    try:
                        storyboard = load_storyboard(path)
                    except Exception as exc:
                        self._set_pane_status("prompt-status", f"Invalid storyboard: {exc}")
                        self._set_status("That file is not a valid storyboard.", "error")
                        return
                    self.settings.prompt = ""
                    self.settings.storyboard_path = path
                    self._show_storyboard(storyboard, f"file: {path.name}")
                    self._goto("storyboard")
                    return

                self._set_status("Choose how to start.", "error")

            def _validate_storyboard(self) -> bool:
                if self.storyboard is None:
                    self._set_pane_status(
                        "storyboard-status", "The scene plan will be created at render time."
                    )
                    return True

                raw = self._q("#storyboard-json", w["TextArea"]).text
                try:
                    storyboard = Storyboard.model_validate(json.loads(raw))
                except json.JSONDecodeError as exc:
                    self._set_pane_status(
                        "storyboard-status", f"JSON error at line {exc.lineno}: {exc.msg}"
                    )
                    self._set_status("Storyboard JSON is not valid JSON.", "error")
                    return False
                except Exception as exc:
                    self._set_pane_status("storyboard-status", f"Schema error: {exc}")
                    self._set_status("Storyboard does not match the schema.", "error")
                    return False

                errors = default_registry().validate(storyboard)
                if errors:
                    preview = "; ".join(errors[:3])
                    self._set_pane_status(
                        "storyboard-status", f"{len(errors)} problem(s): {preview}"
                    )
                    self._set_status(
                        "Storyboard uses components or params that cannot render.", "error"
                    )
                    return False

                self.storyboard = storyboard
                self._refresh_table()
                self._refresh_duration()
                self._set_pane_status("storyboard-status", "Valid.")
                self._set_status("Storyboard validated.", "ok")
                return True

            # -- rendering -------------------------------------------------

            def _start_render(self) -> None:
                if self.busy:
                    self._set_status("A render is already running.", "busy")
                    return
                self._sync_settings()
                if self.storyboard is None and not self.settings.prompt.strip():
                    self._set_status(
                        "Nothing to render: add a prompt or load a storyboard.", "error"
                    )
                    return

                self._goto("render")
                log = self._q("#render-log", w["RichLog"])
                log.clear()
                self._render_log_lines.clear()
                self._q("#copy-render-log", w["Button"]).disabled = True
                self._append_render_log("Starting render", style="b")
                self._append_render_log(
                    f"quality={self.settings.quality}  theme={self.settings.theme}  "
                    f"captions={'on' if self.settings.captions else 'off'}"
                )
                self._append_render_log(f"output={self.settings.output_dir}")

                self.busy = True
                self.cancel_event.clear()
                self.result = None
                self.started_at = time.monotonic()
                self._progress_label = "starting"
                self._logged_label = ""
                self._q("#render-stage", w["Static"]).update("Working…")
                self._q("#render-summary", w["Static"]).update("")
                self._q("#render-details", w["Collapsible"]).collapsed = True
                self._q("#progress-bar", w["ProgressBar"]).update(total=None, progress=0)
                self._q("#back", w["Button"]).disabled = True
                self._q("#start", w["Button"]).disabled = True
                self._q("#cancel", w["Button"]).disabled = False
                self._q("#open-video", w["Button"]).disabled = True
                self._set_status("Rendering…", "busy")
                self._timer = self.set_interval(0.5, self._tick)
                self._render_worker()

            def _tick(self) -> None:
                if not self.busy:
                    return
                elapsed = time.monotonic() - self.started_at
                self._q("#render-stage", w["Static"]).update(
                    f"{self._progress_label}  ·  {elapsed:0.0f}s"
                )

            # -- progress from the worker thread --------------------------

            def _worker_progress(self, event: Any) -> None:
                """Runs in the render thread; hop to the UI thread."""
                self.call_from_thread(self._apply_progress, event)

            def _apply_progress(self, event: Any) -> None:
                if not self.busy:
                    return
                bar = self._q("#progress-bar", w["ProgressBar"])
                if event.total > 0:
                    # determinate: units the pipeline can actually observe
                    bar.update(total=event.total, progress=event.done)
                else:
                    # the amount of work is still unknown; do not pretend
                    bar.update(total=None, progress=0)
                self._progress_label = event.label or self._progress_label
                if event.label and event.label != self._logged_label:
                    self._logged_label = event.label
                    self._append_render_log(event.label, style="dim")
                elapsed = time.monotonic() - self.started_at
                self._q("#render-stage", w["Static"]).update(
                    f"{self._progress_label}  ·  {elapsed:0.0f}s"
                )

            @w["work"](thread=True, exclusive=True)
            def _render_worker(self) -> None:
                try:
                    storyboard_path = None
                    if self.storyboard is not None:
                        tmp_dir = Path(tempfile.mkdtemp(prefix="animatica-tui-"))
                        storyboard_path = tmp_dir / "storyboard.json"
                        dump_storyboard(self.storyboard, storyboard_path)

                    result = make_video(
                        prompt=(self.settings.prompt or None) if storyboard_path is None else None,
                        storyboard_path=storyboard_path,
                        out_dir=self.settings.output_dir,
                        preview=(self.settings.quality == "preview"),
                        quality=self.settings.quality,
                        provider=self.settings.provider,
                        captions=self.settings.captions,
                        frame_lint=self.settings.frame_lint,
                        vertical=self.settings.vertical,
                        theme=self.settings.theme,
                        on_progress=self._worker_progress,
                    )
                    if self.cancel_event.is_set():
                        self.call_from_thread(self._render_cancelled)
                    else:
                        self.call_from_thread(self._render_done, result)
                except StoryboardGenerationError as exc:
                    self.call_from_thread(
                        self._render_failed,
                        "Storyboard generation failed",
                        list(exc.errors[:6]),
                    )
                except (ProviderError, RateLimited) as exc:
                    self.call_from_thread(self._render_failed, "Provider error", [str(exc)])
                except Exception as exc:  # noqa: BLE001 - surface everything in the log
                    self.call_from_thread(
                        self._render_failed,
                        "Render failed",
                        [f"{type(exc).__name__}: {exc}"],
                    )

            def _stop_timer(self) -> None:
                if self._timer is not None:
                    self._timer.stop()
                    self._timer = None

            def _finish(self) -> None:
                self._stop_timer()
                self.busy = False
                self._q("#start", w["Button"]).disabled = False
                self._q("#cancel", w["Button"]).disabled = True
                self._q("#back", w["Button"]).disabled = self._current_step() == "prompt"

            def _render_done(self, result: MakeResult) -> None:
                self._finish()
                self.result = result
                self._q("#render-stage", w["Static"]).update("Complete.")
                bar = self._q("#progress-bar", w["ProgressBar"])
                # keep the real unit scale when the pipeline reported one
                scale = bar.total or 100
                bar.update(total=scale, progress=scale)
                self._q("#open-video", w["Button"]).disabled = False

                summary = [f"video: {result.video}", f"report: {result.report}"]
                if result.warnings:
                    summary.append(f"{len(result.warnings)} warning(s) — see the log")
                self._q("#render-summary", w["Static"]).update("\n".join(summary))

                self._append_render_log(f"done {result.video}", style="b green")
                for warning in result.warnings:
                    self._append_render_log(f"warning {warning}", style="yellow")
                if result.warnings:
                    self._q("#render-details", w["Collapsible"]).collapsed = False
                self._set_status(f"Done in {time.monotonic() - self.started_at:0.1f}s.", "ok")

            def _render_failed(self, title: str, lines: list[str]) -> None:
                self._finish()
                self._q("#render-stage", w["Static"]).update(title)
                self._append_render_log(title, style="b red")
                for line in lines:
                    self._append_render_log(f"  {line}")
                self._q("#render-details", w["Collapsible"]).collapsed = False
                self._set_status(f"{title}. See the details below.", "error")

            def _render_cancelled(self) -> None:
                self._finish()
                self._q("#render-stage", w["Static"]).update("Cancelled.")
                self._append_render_log("cancelled", style="yellow")
                self._q("#render-details", w["Collapsible"]).collapsed = False
                self._set_status("Render cancelled.", "busy")

            # -- events ----------------------------------------------------

            def on_filter_select_changed(self, event: Any) -> None:
                self._choice_changed(getattr(event.filter_select, "id", "") or "")

            def on_select_changed(self, event: Any) -> None:
                widget_id = getattr(event.select, "id", "") or ""
                if widget_id == "source-mode":
                    self._apply_source_mode(str(event.value or "prompt"))
                self._choice_changed(widget_id)

            def _choice_changed(self, widget_id: str) -> None:
                self._sync_settings()
                self._update_topbar()
                if widget_id == "provider-select" and self.storyboard is None:
                    self.source_label = "prompt"
                    self._q("#side-source", w["Static"]).update("Source: prompt")
                # Job choices are remembered for the next launch.
                if widget_id != "source-mode":
                    self._save_defaults()

            def on_switch_changed(self, event: Any) -> None:
                self._sync_settings()
                self._save_defaults()

            def on_input_changed(self, event: Any) -> None:
                if event.input.id == "prompt-input":
                    if self._q("#source-mode", w["Select"]).value == "prompt":
                        self.settings.prompt = event.value.strip()
                elif event.input.id == "sb-path-input":
                    if self._q("#source-mode", w["Select"]).value == "storyboard":
                        self.settings.storyboard_path = _path_from_input(event.value)
                elif event.input.id == "output-dir":
                    output_dir = _path_from_input(event.value, DEFAULT_OUTPUT_DIR)
                    assert output_dir is not None
                    self.settings.output_dir = output_dir
                    self._q("#output-summary", w["Static"]).update(
                        f"Saving to {self.settings.output_dir} · change under More options"
                    )
                    existing = self.settings.existing_outputs()
                    warning = self._q("#overwrite-warning", w["Static"])
                    warning.update(f"Will overwrite: {', '.join(existing)}" if existing else "")
                    warning.display = bool(existing)

            def on_button_pressed(self, event: Any) -> None:
                button_id = getattr(event.button, "id", "")
                if button_id == "next":
                    self._continue()
                elif button_id == "back":
                    self.action_prev_step()
                elif button_id == "topbar-help":
                    self.push_screen(HelpScreen())
                elif button_id == "clear":
                    self._q("#source-mode", w["Select"]).value = "prompt"
                    self._apply_source_mode("prompt")
                    self._q("#prompt-input", w["Input"]).value = ""
                    self._q("#sb-path-input", w["Input"]).value = ""
                    self._q("#template-select", w["Select"]).clear()
                    self.storyboard = None
                    self.source_label = "—"
                    self.settings.prompt = ""
                    self.settings.storyboard_path = None
                    self._q("#side-source", w["Static"]).update("Source: —")
                    self._q("#storyboard-empty", w["Static"]).display = True
                    self._q("#storyboard-details").display = False
                    self._refresh_duration()
                    self._set_pane_status("prompt-status", "")
                    self._set_status("Cleared.")
                elif button_id == "validate":
                    self._validate_storyboard()
                elif button_id == "reload":
                    if self.storyboard is not None:
                        self._show_storyboard(self.storyboard, self.source_label)
                        self._set_status("Reloaded the loaded storyboard.", "ok")
                    else:
                        self._set_status("Nothing loaded to reload.", "error")
                elif button_id == "start":
                    self._start_render()
                elif button_id == "cancel":
                    self._cancel_render()
                elif button_id == "open-video":
                    self._open_video()
                elif button_id == "copy-render-log":
                    self._copy_render_log()

            # -- actions ---------------------------------------------------

            def _continue(self) -> None:
                step = self._current_step()
                if step == "prompt":
                    self._advance_from_prompt()
                elif step == "storyboard":
                    if self._validate_storyboard():
                        self._goto("job")
                elif step == "job":
                    self._sync_settings()
                    self._save_defaults()
                    self._refresh_job_summary()
                    self._goto("render")
                elif step == "render":
                    self._start_render()

            def action_next_step(self) -> None:
                self._continue()

            def action_prev_step(self) -> None:
                if self.busy:
                    self._set_status("Wait for the render to finish before going back.", "busy")
                    return
                step = self._current_step()
                index = STEPS.index(step)
                if index > 0:
                    self._goto(STEPS[index - 1])

            def action_start_render(self) -> None:
                self._start_render()

            def action_copy_render_log(self) -> None:
                self._copy_render_log()

            def action_help(self) -> None:
                self.push_screen(HelpScreen())

            def action_validate(self) -> None:
                self._validate_storyboard()

            def _cancel_render(self) -> None:
                if not self.busy:
                    return
                self.cancel_event.set()
                self._append_render_log(
                    "cancel requested — stops at the next stage boundary", style="yellow"
                )
                self._set_status("Cancelling after the current stage…", "busy")

            def _open_video(self) -> None:
                if self.result is None:
                    return
                path = self.result.video
                try:
                    if sys.platform == "win32":
                        os.startfile(path)  # type: ignore[attr-defined]
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", str(path)])
                    else:
                        subprocess.Popen(["xdg-open", str(path)])
                    self._set_status(f"Opening {path.name}…", "")
                except Exception as exc:  # noqa: BLE001
                    self._set_status(f"Could not open the video: {exc}", "error")

        app = StudioApp()
        wrapper._app = app
        return app

    def run(self) -> None:
        """Start the Textual application."""
        self.create_app().run()


def run_tui() -> None:
    """Public entry point: launch the Animatica studio.

    Raises a clear error if ``textual`` is not installed.
    """
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "The 'tui' command requires the optional 'textual' package. "
            "Install it with:  pip install 'animatica[tui]'  "
            f"(import failed: {exc})"
        ) from exc
    AnimaticaTuiApp().run()

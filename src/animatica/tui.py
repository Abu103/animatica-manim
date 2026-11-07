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
        from textual.widgets import (
            Button,
            DataTable,
            Footer,
            Input,
            ProgressBar,
            RichLog,
            Select,
            Static,
            Switch,
            TabbedContent,
            TabPane,
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
        "ComposeResult": ComposeResult,
        "DataTable": DataTable,
        "Footer": Footer,
        "Grid": Grid,
        "Horizontal": Horizontal,
        "Input": Input,
        "ProgressBar": ProgressBar,
        "RichLog": RichLog,
        "FilterSelect": FilterSelect,
        "Select": Select,
        "Static": Static,
        "Switch": Switch,
        "TabbedContent": TabbedContent,
        "TabPane": TabPane,
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

STEPS = ("prompt", "storyboard", "job", "render")


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

APP_CSS = """
Screen {
    background: #0b151b;
    color: #eef4ef;
}

/* ---- top bar -------------------------------------------------------- */
#topbar {
    height: 3;
    padding: 1 2 0 2;
    background: #10222a;
    border-bottom: solid #24424a;
}
#topbar .brand {
    width: auto;
    text-style: bold;
    color: #a5f5cc;
    margin-right: 2;
}
#topbar .tagline {
    width: 1fr;
    color: #6f8f8b;
}
#topbar .step {
    width: auto;
    color: #9fbdb5;
}

/* ---- main split ------------------------------------------------------ */
#content { height: 1fr; }

/* job step: a two-column form grid (label, control) */
#job-grid {
    grid-size: 4;
    grid-columns: 13 1fr 13 1fr;
    grid-gutter: 0 1;
    height: auto;
}
#job-grid .field-label {
    color: #9fbdb5;
    height: 3;
    content-align: left middle;
}
#job-grid Input, #job-grid Select, #job-grid FilterSelect { width: 1fr; }
#job-grid FilterSelect { height: auto; }
#job-grid FilterSelect #fs-list { background: #10231f; }
#job-grid Switch { height: 3; }
.warn { color: #ffad95; margin-top: 1; }
.side-value { color: #cfe3dc; }
.side-head { height: 1; }
.side-head #side-duration { margin-left: 3; }

/* ---- tabs ------------------------------------------------------------ */
TabbedContent { height: 1fr; }
TabPane { padding: 0 2; overflow-y: auto; height: 1fr; }

.pane-title {
    margin-top: 1;
    text-style: bold;
    color: #eef4ef;
    margin-bottom: 1;
}
.hint { color: #6f8f8b; }
.field-label { color: #9fbdb5; margin-top: 1; }
.row { height: auto; margin-top: 1; }

Input, TextArea { border: tall #24424a; background: #0a141b; }
SelectCurrent { border: tall #24424a; background: #0a141b; }
Input:focus, TextArea:focus { border: tall #a5f5cc; }
Select:focus > SelectCurrent { border: tall #a5f5cc; }
SelectOverlay { border: tall #24424a; }
Button { margin-right: 1; min-width: 14; }
Button.-primary { background: #a5f5cc; color: #07231c; text-style: bold; }
Button.-error { background: #ffad95; color: #3a1f18; }

/* storyboard step */
/* heights are computed in _layout_storyboard: fr/% rounding inside a
   scrolling pane made the editor overflow the last screen row */
#storyboard-table { min-height: 4; border: round #24424a; }
#storyboard-json { min-height: 4; }
#storyboard-json { height: 1fr; min-height: 6; }

/* render step */
#render-stage { color: #cfe3dc; }
#progress-bar { margin: 1 0; }
#render-log {
    height: 1fr;
    min-height: 6;
    border: round #24424a;
    background: #081014;
    padding: 0 1;
}
#render-summary { color: #cfe3dc; margin-top: 1; }

/* ---- status line ----------------------------------------------------- */
#status {
    height: 1;
    padding: 0 2;
    background: #10222a;
    color: #9fbdb5;
}
#status.ok { color: #a5f5cc; }
#status.error { color: #ffad95; }
#status.busy { color: #f0c97f; }
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

        class StudioApp(w["App"]):
            CSS = APP_CSS
            TITLE = "Animatica"
            BINDINGS = [
                w["Binding"]("ctrl+j", "next_step", "Next step"),
                w["Binding"]("ctrl+b", "prev_step", "Previous step"),
                w["Binding"]("ctrl+r", "start_render", "Render"),
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

            # -- layout ----------------------------------------------------

            def compose(self) -> w["ComposeResult"]:  # type: ignore[valid-type]
                with w["Horizontal"](id="topbar"):
                    yield w["Static"]("◆ Animatica", classes="brand")
                    yield w["Static"]("prompt → explainer video", id="tagline", classes="tagline")
                    yield w["Static"]("", id="topbar-step", classes="step")

                with w["Vertical"](id="content"):
                    with w["TabbedContent"](initial="pane-prompt", id="steps"):
                        with w["TabPane"]("1 · Prompt", id="pane-prompt"):
                            yield from self._compose_prompt()
                        with w["TabPane"]("2 · Storyboard", id="pane-storyboard"):
                            yield from self._compose_storyboard()
                        with w["TabPane"]("3 · Job", id="pane-job"):
                            yield from self._compose_job()
                        with w["TabPane"]("4 · Render", id="pane-render"):
                            yield from self._compose_render()

                yield w["Static"]("Ready. Start with a prompt or an offline template.", id="status")
                yield w["Footer"]()

            def _compose_prompt(self):
                yield w["Static"]("What should the video explain?", classes="pane-title")
                yield w["Input"](
                    placeholder="prompt · e.g. explain the pythagorean theorem", id="prompt-input"
                )
                template_options = [(name, name) for name, _ in TemplateMatcher().list_templates()]
                yield w["Select"](
                    options=template_options,
                    allow_blank=True,
                    prompt="…or pick an offline template (no API key)",
                    id="template-select",
                )
                yield w["Input"](
                    placeholder="…or open an existing storyboard.json", id="sb-path-input"
                )
                yield w["Static"]("Use exactly one of the three.", classes="hint")
                with w["Horizontal"](classes="row"):
                    yield w["Button"]("Continue →", id="next", variant="primary")
                    yield w["Button"]("Clear", id="clear")
                yield w["Static"]("", id="prompt-status", classes="hint")

            def _compose_storyboard(self):
                yield w["Static"]("Review the scenes before spending render time", classes="pane-title")
                with w["Horizontal"](classes="row"):
                    yield w["Button"]("Validate", id="validate", variant="primary")
                    yield w["Button"]("Reload", id="reload")
                    yield w["Button"]("Continue →", id="to-render")
                    yield w["Static"]("", id="storyboard-status", classes="hint")
                yield w["DataTable"](id="storyboard-table", zebra_stripes=True)
                yield w["TextArea"](id="storyboard-json", language="json")

            def _compose_render(self):
                yield w["Static"]("Render", classes="pane-title")
                yield w["Static"]("Not started.", id="render-stage")
                yield w["ProgressBar"](id="progress-bar", total=None, show_eta=False)
                with w["Horizontal"](classes="row"):
                    yield w["Button"]("Start render", id="start", variant="primary")
                    yield w["Button"]("Cancel", id="cancel", variant="error", disabled=True)
                    yield w["Button"]("Open video", id="open-video", disabled=True)
                yield w["Static"]("", id="render-summary")
                yield w["RichLog"](id="render-log", markup=True, wrap=True)

            def _compose_job(self):
                yield w["Static"]("Job settings", classes="pane-title")
                with w["Horizontal"](classes="side-head"):
                    yield w["Static"]("source: —", id="side-source", classes="side-value")
                    yield w["Static"]("", id="side-duration", classes="side-value")

                with w["Grid"](id="job-grid"):
                    yield w["Static"]("Output folder", classes="field-label")
                    yield w["Input"](value=str(self.settings.output_dir), id="output-dir")
                    yield w["Static"]("Orientation", classes="field-label")
                    yield w["FilterSelect"](
                        options=ORIENTATION_CHOICES,
                        value=self.settings.orientation,
                        id="orientation-select",
                    )

                    yield w["Static"]("Quality", classes="field-label")
                    yield w["FilterSelect"](
                        options=QUALITY_CHOICES, value=self.settings.quality, id="quality-select"
                    )
                    yield w["Static"]("Provider", classes="field-label")
                    yield w["FilterSelect"](
                        options=PROVIDER_CHOICES, value=self.settings.provider, id="provider-select"
                    )

                    yield w["Static"]("Theme", classes="field-label")
                    yield w["FilterSelect"](
                        options=THEME_CHOICES, value=self.settings.theme, id="theme-select"
                    )
                    yield w["Static"]("Burn captions", classes="field-label")
                    yield w["Switch"](value=self.settings.captions, id="captions-switch")

                    yield w["Static"]("Frame lint", classes="field-label")
                    yield w["Switch"](value=self.settings.frame_lint, id="frame-lint-switch")
                    yield w["Static"]("", classes="field-label")
                    yield w["Static"]("", classes="field-label")

                yield w["Static"](
                    "Template runs offline; other providers need an API key.",
                    id="provider-hint",
                    classes="hint",
                )
                yield w["Static"]("", id="overwrite-warning", classes="warn")

            def on_mount(self) -> None:
                self._layout_storyboard()
                self._refresh_sidebar()
                self._set_status("Ready. Start with a prompt or an offline template.")

            # -- small helpers --------------------------------------------

            def _q(self, selector: str, *types: Any) -> Any:
                return self.query_one(selector, *types)

            def _set_status(self, message: str, kind: str = "") -> None:
                status = self._q("#status", w["Static"])
                status.update(message)
                status.classes = kind

            def _set_pane_status(self, widget_id: str, message: str) -> None:
                self._q(f"#{widget_id}", w["Static"]).update(message)

            #: Where focus should land when a step becomes active. This is not
            #: cosmetic: TabbedContent re-activates the pane that contains the
            #: focused widget, so leaving focus on the button we just clicked
            #: (now hidden) would immediately switch the step back.
            _FOCUS_TARGETS = {
                "prompt": "#prompt-input",
                "storyboard": "#validate",
                "job": "#output-dir",
                "render": "#start",
            }

            def _goto(self, step: str) -> None:
                self._q("#steps", w["TabbedContent"]).active = f"pane-{step}"
                if step in self._FOCUS_TARGETS:
                    self.call_after_refresh(self._focus, step)
                self._update_topbar()

            def on_resize(self, event: Any) -> None:
                # 80 columns is a supported size; the tagline is the first thing
                # to go when the topbar cannot fit both texts.
                tagline = self._q("#tagline", w["Static"])
                tagline.display = event.size.width >= 96
                self._layout_storyboard()

            #: rows taken by chrome around a step: topbar 3, tabs 2, status 1, footer 1
            _CHROME_ROWS = 7

            def _layout_storyboard(self) -> None:
                """Split the storyboard step between the scene table and the editor.

                Both widgets are sized explicitly: fractional heights are rounded
                per widget inside a scrolling pane, which pushed the editor's last
                row over the status bar at 80x24.
                """
                try:
                    pane_rows = max(8, self.size.height - self._CHROME_ROWS)
                    space = max(8, pane_rows - 6)  # heading, 2 margins, button row
                    table_rows = max(4, min(12, space // 2))
                    editor_rows = max(4, space - table_rows)
                    self._q("#storyboard-table", w["DataTable"]).styles.height = table_rows
                    self._q("#storyboard-json", w["TextArea"]).styles.height = editor_rows
                except Exception:
                    pass

            def _focus(self, step: str) -> None:
                try:
                    self._q(self._FOCUS_TARGETS[step]).focus()
                except Exception:  # disabled/hidden targets are not fatal
                    pass
                try:
                    # Focusing a child leaves the pane scrolled by a row, which
                    # hides the step heading. A step always opens at the top.
                    self._q(f"#pane-{step}").scroll_home(animate=False)
                except Exception:
                    pass

            def _current_step(self) -> str:
                active = self._q("#steps", w["TabbedContent"]).active or "pane-prompt"
                return active.replace("pane-", "")

            def _update_topbar(self) -> None:
                step = self._current_step()
                index = STEPS.index(step) + 1 if step in STEPS else 0
                self._q("#topbar-step", w["Static"]).update(
                    f"step {index}/4 · {step} · provider: {self.settings.provider}"
                )

            # -- settings sync --------------------------------------------

            def _sync_settings(self) -> None:
                s = self.settings
                # the prompt lives in a widget, so it must be read live: pressing
                # Start straight from the Render step skips the Prompt step.
                s.prompt = self._q("#prompt-input", w["Input"]).value.strip()
                s.output_dir = Path(self._q("#output-dir", w["Input"]).value.strip() or DEFAULT_OUTPUT_DIR)
                s.quality = str(self._q("#quality-select", w["FilterSelect"]).value or DEFAULT_QUALITY)
                s.theme = str(self._q("#theme-select", w["FilterSelect"]).value or DEFAULT_THEME)
                s.orientation = str(
                    self._q("#orientation-select", w["FilterSelect"]).value or DEFAULT_ORIENTATION
                )
                s.provider = str(self._q("#provider-select", w["FilterSelect"]).value or DEFAULT_PROVIDER)
                s.captions = bool(self._q("#captions-switch", w["Switch"]).value)
                s.frame_lint = bool(self._q("#frame-lint-switch", w["Switch"]).value)

            def _save_defaults(self) -> None:
                _persist_defaults(self.settings)

            def _refresh_sidebar(self) -> None:
                self._sync_settings()
                self._q("#side-source", w["Static"]).update(f"source: {self.source_label}")
                self._update_topbar()
                existing = self.settings.existing_outputs()
                self._q("#overwrite-warning", w["Static"]).update(
                    "These will be overwritten:\n" + "\n".join(f"· {name}" for name in existing)
                    if existing
                    else ""
                )
                self._refresh_duration()

            def _refresh_duration(self) -> None:
                target = self._q("#side-duration", w["Static"])
                if self.storyboard is None:
                    target.update("")
                    return
                registry = default_registry()
                total = 0.0
                for scene in self.storyboard.scenes:
                    for beat in scene.beats:
                        try:
                            component = registry.get(beat.component)
                            total += component.duration(component.Params.model_validate(beat.params))
                        except Exception:  # unknown/invalid component: leave it out
                            continue
                target.update(f"≈ {total:.1f}s · {len(self.storyboard.scenes)} scenes")

            # -- storyboard plumbing --------------------------------------

            def _show_storyboard(self, storyboard: Storyboard, source: str) -> None:
                self.storyboard = storyboard
                self.source_label = source
                self._q("#side-source", w["Static"]).update(f"source: {source}")

                self._refresh_table()
                self._q("#storyboard-json", w["TextArea"]).text = storyboard.model_dump_json(indent=2)
                self._refresh_duration()
                self._set_status(f"Loaded {source}: {len(storyboard.scenes)} scene(s).", "ok")

            def _refresh_table(self) -> None:
                assert self.storyboard is not None
                table = self._q("#storyboard-table", w["DataTable"])
                # the columns are added once and reused: clear(columns=True) plus
                # add_columns in the same tick left the table without rows
                if not table.columns:
                    table.add_columns("scene", "beat", "component", "params", "caption")
                table.clear(columns=False)
                for si, scene in enumerate(self.storyboard.scenes, 1):
                    for bi, beat in enumerate(scene.beats, 1):
                        params = json.dumps(beat.params, ensure_ascii=False)
                        if len(params) > 48:
                            params = params[:45] + "…"
                        table.add_row(str(si), str(bi), beat.component, params, beat.caption or "—")
                if table.row_count:
                    table.move_cursor(row=0, column=0)
                table.scroll_home(animate=False)

            def _advance_from_prompt(self) -> None:
                prompt = self._q("#prompt-input", w["Input"]).value.strip()
                sb_path_text = self._q("#sb-path-input", w["Input"]).value.strip()
                template_value = self._q("#template-select", w["Select"]).value
                template_name = (
                    str(template_value)
                    if template_value not in (None, w["Select"].NULL, "")
                    else None
                )

                sources = sum(bool(x) for x in (prompt, sb_path_text, template_name))
                if sources == 0:
                    self._set_pane_status(
                        "prompt-status", "Enter a prompt, choose a template, or open a storyboard."
                    )
                    self._set_status("Nothing selected yet.", "error")
                    return
                if sources > 1:
                    self._set_pane_status(
                        "prompt-status", "Pick only one: prompt, template, or storyboard file."
                    )
                    self._set_status("Two sources are set; choose one.", "error")
                    return

                self.settings.prompt = prompt
                self._sync_settings()

                if sb_path_text:
                    path = Path(sb_path_text).expanduser()
                    if not path.is_file():
                        self._set_pane_status("prompt-status", f"Not found: {sb_path_text}")
                        self._set_status("Storyboard file not found.", "error")
                        return
                    try:
                        self._show_storyboard(load_storyboard(path), f"file: {path.name}")
                    except Exception as exc:
                        self._set_pane_status("prompt-status", f"Invalid storyboard: {exc}")
                        self._set_status("That file is not a valid storyboard.", "error")
                        return
                    self._goto("storyboard")
                    return

                if template_name:
                    storyboard = TemplateMatcher().by_name(template_name)
                    if storyboard is None:
                        self._set_pane_status("prompt-status", f"Template {template_name!r} not found.")
                        self._set_status("Template not found.", "error")
                        return
                    self._show_storyboard(storyboard, f"template: {template_name}")
                    self._goto("storyboard")
                    return

                # Prompt only: the storyboard is generated during render.
                self.storyboard = None
                self.source_label = f"prompt ({self.settings.provider})"
                self._q("#side-source", w["Static"]).update(f"source: {self.source_label}")
                self._q("#side-duration", w["Static"]).update("")
                self._q("#prompt-status", w["Static"]).update(
                    f"Will ask {self.settings.provider} for a storyboard at render time."
                )
                self._set_status("Prompt set. Continue to Render when ready.", "ok")
                self._goto("render")

            def _validate_storyboard(self) -> None:
                raw = self._q("#storyboard-json", w["TextArea"]).text
                try:
                    storyboard = Storyboard.model_validate(json.loads(raw))
                except json.JSONDecodeError as exc:
                    self._set_pane_status("storyboard-status", f"JSON error at line {exc.lineno}: {exc.msg}")
                    self._set_status("Storyboard JSON is not valid JSON.", "error")
                    return
                except Exception as exc:
                    self._set_pane_status("storyboard-status", f"Schema error: {exc}")
                    self._set_status("Storyboard does not match the schema.", "error")
                    return

                errors = default_registry().validate(storyboard)
                if errors:
                    preview = "; ".join(errors[:3])
                    self._set_pane_status("storyboard-status", f"{len(errors)} problem(s): {preview}")
                    self._set_status("Storyboard uses components or params that cannot render.", "error")
                    return

                self.storyboard = storyboard
                self._refresh_table()
                self._refresh_duration()
                self._set_pane_status("storyboard-status", "Valid.")
                self._set_status("Storyboard validated.", "ok")

            # -- rendering -------------------------------------------------

            def _start_render(self) -> None:
                if self.busy:
                    self._set_status("A render is already running.", "busy")
                    return
                self._sync_settings()
                if self.storyboard is None and not self.settings.prompt.strip():
                    self._set_status("Nothing to render: add a prompt or load a storyboard.", "error")
                    return

                self._goto("render")
                log = self._q("#render-log", w["RichLog"])
                log.clear()
                log.write("[b]Starting render[/b]")
                log.write(f"quality={self.settings.quality}  theme={self.settings.theme}  "
                          f"captions={'on' if self.settings.captions else 'off'}")
                log.write(f"output={self.settings.output_dir}")

                self.busy = True
                self.cancel_event.clear()
                self.result = None
                self.started_at = time.monotonic()
                self._progress_label = "starting"
                self._logged_label = ""
                self._q("#render-stage", w["Static"]).update("Working…")
                self._q("#render-summary", w["Static"]).update("")
                self._q("#progress-bar", w["ProgressBar"]).update(total=None, progress=0)
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
                    self._q("#render-log", w["RichLog"]).write(f"[dim]{event.label}[/dim]")
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
                    self.call_from_thread(self._render_failed, "Storyboard generation failed", list(exc.errors[:6]))
                except (ProviderError, RateLimited) as exc:
                    self.call_from_thread(self._render_failed, "Provider error", [str(exc)])
                except Exception as exc:  # noqa: BLE001 - surface everything in the log
                    self.call_from_thread(self._render_failed, "Render failed", [f"{type(exc).__name__}: {exc}"])

            def _stop_timer(self) -> None:
                if self._timer is not None:
                    self._timer.stop()
                    self._timer = None

            def _finish(self) -> None:
                self._stop_timer()
                self.busy = False
                self._q("#start", w["Button"]).disabled = False
                self._q("#cancel", w["Button"]).disabled = True

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

                log = self._q("#render-log", w["RichLog"])
                log.write(f"[b green]done[/b green] {result.video}")
                for warning in result.warnings:
                    log.write(f"[yellow]warning[/yellow] {warning}")
                self._set_status(f"Done in {time.monotonic() - self.started_at:0.1f}s.", "ok")

            def _render_failed(self, title: str, lines: list[str]) -> None:
                self._finish()
                self._q("#render-stage", w["Static"]).update(title)
                log = self._q("#render-log", w["RichLog"])
                log.write(f"[b red]{title}[/b red]")
                for line in lines:
                    log.write(f"  {line}")
                self._set_status(f"{title}. See the log.", "error")

            def _render_cancelled(self) -> None:
                self._finish()
                self._q("#render-stage", w["Static"]).update("Cancelled.")
                self._q("#render-log", w["RichLog"]).write("[yellow]cancelled[/yellow]")
                self._set_status("Render cancelled.", "busy")

            # -- events ----------------------------------------------------

            def on_filter_select_changed(self, event: Any) -> None:
                self._choice_changed(getattr(event.filter_select, "id", "") or "")

            def on_select_changed(self, event: Any) -> None:
                self._choice_changed(getattr(event.select, "id", "") or "")

            def _choice_changed(self, widget_id: str) -> None:
                self._sync_settings()
                self._update_topbar()
                if (
                    widget_id == "provider-select"
                    and self.storyboard is None
                    and self.settings.prompt.strip()
                ):
                    self.source_label = f"prompt ({self.settings.provider})"
                    self._q("#side-source", w["Static"]).update(f"source: {self.source_label}")
                # choices are the user's defaults: remember them for next launch
                self._save_defaults()

            def on_switch_changed(self, event: Any) -> None:
                self._sync_settings()
                self._save_defaults()

            def on_input_changed(self, event: Any) -> None:
                if event.input.id == "prompt-input":
                    self.settings.prompt = event.value.strip()
                elif event.input.id == "output-dir":
                    self.settings.output_dir = Path(event.value.strip() or DEFAULT_OUTPUT_DIR)
                    existing = self.settings.existing_outputs()
                    self._q("#overwrite-warning", w["Static"]).update(
                        "These will be overwritten:\n"
                        + "\n".join(f"· {name}" for name in existing)
                        if existing
                        else ""
                    )

            def on_button_pressed(self, event: Any) -> None:
                button_id = getattr(event.button, "id", "")
                if button_id == "next":
                    self._advance_from_prompt()
                elif button_id == "clear":
                    self._q("#prompt-input", w["Input"]).value = ""
                    self._q("#sb-path-input", w["Input"]).value = ""
                    self._q("#template-select", w["Select"]).clear()
                    self._set_pane_status("prompt-status", "")
                    self._set_status("Cleared.", "")
                elif button_id == "validate":
                    self._validate_storyboard()
                elif button_id == "reload":
                    if self.storyboard is not None:
                        self._show_storyboard(self.storyboard, self.source_label)
                        self._set_status("Reloaded the loaded storyboard.", "ok")
                    else:
                        self._set_status("Nothing loaded to reload.", "error")
                elif button_id == "to-render":
                    self._goto("render")
                elif button_id == "start":
                    self._start_render()
                elif button_id == "cancel":
                    self._cancel_render()
                elif button_id == "open-video":
                    self._open_video()

            # -- actions ---------------------------------------------------

            def action_next_step(self) -> None:
                step = self._current_step()
                if step == "prompt":
                    self._advance_from_prompt()
                elif step == "storyboard":
                    self._goto("render")
                else:
                    self._start_render()

            def action_prev_step(self) -> None:
                step = self._current_step()
                index = STEPS.index(step)
                if index > 0:
                    self._goto(STEPS[index - 1])

            def action_start_render(self) -> None:
                self._start_render()

            def action_validate(self) -> None:
                self._validate_storyboard()

            def _cancel_render(self) -> None:
                if not self.busy:
                    return
                self.cancel_event.set()
                self._q("#render-log", w["RichLog"]).write(
                    "[yellow]cancel requested[/yellow] — stops at the next stage boundary"
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

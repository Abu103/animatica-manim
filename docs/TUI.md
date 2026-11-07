# Animatica Studio (TUI)

`animatica tui` (or `python -m animatica tui`) opens Studio: one screen, four
steps, keyboard first. It is the guided path from an idea to a finished video
without remembering flags.

```
1 · Prompt   2 · Storyboard   3 · Job   4 · Render
```

| Step | What it is for |
| --- | --- |
| **1 · Prompt** | Type a prompt, pick an offline template, or open an existing `storyboard.json`. |
| **2 · Storyboard** | The scenes and beats as a table; the raw JSON next to it, editable and validated on demand. |
| **3 · Job** | Where the video goes and how it is made: output folder, quality, theme, orientation, provider, captions, frame lint. |
| **4 · Render** | Start, watch, cancel. Elapsed time, a live log, and the result with any warnings. |

## Keys

| Key | Action |
| --- | --- |
| `ctrl+j` | next step |
| `ctrl+b` | previous step |
| `ctrl+r` | start the render |
| `ctrl+s` | validate the storyboard JSON |
| `ctrl+q` | quit |
| `tab` / `shift+tab` | move between controls |
| `ctrl+p` | command palette |

## Design rules

These are the things the screen is *not* allowed to do. They are covered by
`tests/test_tui.py`, which drives the real app at 80x24.

- **80x24 is the smallest supported terminal.** Every control of a step must be
  reachable there. Panes scroll rather than clip, the tagline disappears below
  96 columns, and the storyboard table/editor split is computed from the screen
  height instead of using fractional heights (fractions round per widget and
  pushed the editor's last row over the status bar).
- **Exactly one source.** A prompt, a template, or a storyboard file. Zero or
  two is an error with a reason, not a silent default.
- **No fake progress.** The bar counts *observable units*: one per scene the
  backend actually finished, then one each for transcode, frame lint and
  captions + report. While the amount of work is still unknown (storyboard
  generation, a cached render, a backend that reports nothing) the bar is
  indeterminate and says so instead of showing a percentage. Elapsed time,
  log lines and the result are all real. Cancelling asks the worker to stop and
  says clearly whether it stopped.
- **Validate before spending time.** Loading a storyboard validates it against
  the model *and* the component registry, so an unknown component is caught
  before manim starts.
- **Say what will be overwritten.** If the output folder already holds
  `video.mp4`, `report.json` or `media/`, the Job step lists them.
- Focus follows the step: `TabbedContent` re-activates whichever pane contains
  the focused widget, so leaving focus on the button that was just clicked would
  bounce the user back a step.

## Progress model

`animatica.progress` defines `ProgressEvent(stage, label, done, total, finished)`
and a `ProgressTracker`. A backend receives `RenderOptions.progress`, a simple
`(label, done, total)` reporter on *its own* unit scale; the first call fixes the
whole-run total (backend units + post-processing units). `make_video` accepts
`on_progress` and emits the post-processing units itself, then a final event
with `finished=True` and `done == total`.

The same events drive the CLI: `animatica make` shows a single rewritten line on
stderr (`[████░░░░]  50%  scene 2/4: done · 12s`), kept live between events by a
ticker that only redraws the elapsed clock. `--no-progress` silences it, and it
is off automatically when stderr is not a terminal so build logs stay clean.
With a redirected stream it prints one plain line per new stage instead.

Backends are expected to report only what they can see: the manim backend emits
one unit per scene (it shells out per scene), the hyperframes backend emits three
coarse units because its render is a single opaque CLI call.

## Non-UI modules touched

`TemplateMatcher.by_name()` was added because `match()` is keyword-based and
takes a *prompt*: `"title_card"` has no whole-word boundary before the
underscore, so the TUI could never load a template by name.

## Choosing values (type to filter)

The Job step's quality, theme, orientation and provider fields are searchable
pickers, not arrow-key-only menus: focus the field and start typing. Matching is
case-insensitive, matches the label or the stored value, and falls back to a
subsequence match (`hg` finds *High 1080p*). `↑`/`↓` walk the matches, `Enter`
takes one, `Esc` closes without changing anything, and the current choice stays
visible as the placeholder.

Your choices are saved to `config.toml` (`quality`, `theme`, `orientation`,
`captions`, `frame_lint`) and restored next launch, so the TUI is the only place
you need to configure anything. The provider is deliberately *not* persisted: a
cloud provider chosen without a key or consent would break the next render.
Set it with `animatica setup` if you want it to stick.

# Animatica Studio (TUI)

`animatica tui` (or `python -m animatica tui`) opens Studio: a focused,
four-step path from an idea to a finished video. It keeps the terminal
simplicity of the CLI while making the next action obvious.

```
IDEA  →  SCENES  →  STYLE  →  RENDER
```

| Step | What it is for |
| --- | --- |
| **Idea** | Describe a topic, choose an offline starter, or open a storyboard file. Only the selected source is active. |
| **Scenes** | Review a readable preview for a starter or file. Prompt-based scenes are created during rendering. Raw JSON is under **Advanced**. |
| **Style** | Keep the recommended quality and format, or open **More options** for provider, theme, output folder, captions, and frame lint. |
| **Render** | Create the video, watch real progress, cancel, review details if needed, and open the result. |

The four steps appear one at a time, with visible **Back** and **Continue**
actions. `F1` or the **Help** button opens the in-app guide. Templates work
offline; an unmatched prompt needs a configured AI provider, available under
**More options**.

## Keys

| Key | Action |
| --- | --- |
| `ctrl+j` | continue to the next step |
| `ctrl+b` | go back one step |
| `ctrl+r` | start a render |
| `ctrl+shift+c` | copy render details to the clipboard |
| `f1` | open or close help |
| `ctrl+q` | quit |
| `tab` / `shift+tab` | move between controls |

On the Render step, **Copy details** copies the complete render log as plain text;
`ctrl+shift+c` does the same. This keeps exception messages and paths available
for pasting into an issue without trying to select text from the terminal.

Mouse and keyboard can both complete the full flow; shortcuts are optional.

## Design rules

These rules are covered by `tests/test_tui.py`, which drives the real app at
80×24 as well as wider sizes.

- **80×24 is the smallest supported terminal.** The current step and navigation
  stay visible. Longer content scrolls; the tagline is hidden below 96 columns.
- **One source at a time.** Choose prompt, starter, or storyboard file from the
  source selector. Alternate controls stay hidden until chosen, so stale input
  cannot conflict with the active source.
- **Progressive disclosure.** Raw storyboard JSON, provider/theme/output
  choices, captions, frame lint, and render logs are behind clearly labeled
  disclosures. The normal path starts with useful defaults.
- **Human-readable preview.** Scene rows describe the visual and narration;
  implementation parameters stay in the advanced JSON editor.
- **No fake progress.** The bar counts *observable units*: one per scene the
  backend actually finished, then one each for transcode, frame lint and
  captions + report. While the amount of work is still unknown (storyboard
  generation, a cached render, a backend that reports nothing) the bar is
  indeterminate and says so instead of showing a percentage. Elapsed time,
  log lines and the result are all real. Cancelling asks the worker to stop and
  says clearly whether it stopped.
- **Validate before spending time.** Loading or editing a storyboard validates
  it against the model *and* component registry, so malformed data or an
  unknown component is caught before rendering.
- **Say what will be overwritten.** If the output folder already holds
  `video.mp4`, `report.json`, or `media/`, the Style step lists them before the
  user starts a render.
- **Accept pasted paths.** Matching single or double quotes around a pasted
  storyboard or output path are removed for file operations, avoiding Windows
  invalid-filename errors. The input retains the text as pasted; summaries and
  render operations use the normalized path.
- **Focus follows navigation.** A step change moves focus to an appropriate
  control, and Back/Continue remain available independently of the scrolling
  step content.

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

Backends report only what they can see: the manim backend emits one unit per
scene (it shells out per scene), and the hyperframes backend emits three coarse
units because its render is a single opaque CLI call.

## Non-UI modules touched

`TemplateMatcher.by_name()` supports exact starter selection because `match()`
is keyword-based and takes a *prompt*: `"title_card"` has no whole-word
boundary before the underscore, so the TUI could not load a starter by name.

## Choosing values (type to filter)

The Style step's quality, theme, orientation, and provider fields are searchable
pickers, not arrow-key-only menus: focus the field and start typing. Matching is
case-insensitive, matches the label or stored value, and falls back to a
subsequence match (`hg` finds *High 1080p*). `↑`/`↓` walk the matches, `Enter`
takes one, `Esc` closes without changing anything, and the current choice stays
visible as the placeholder.

Quality, theme, orientation, captions, and frame-lint choices are saved to
`config.toml` and restored next launch. The provider is deliberately *not*
persisted: a cloud provider chosen without a key or consent would break the next
render. Set it with `animatica setup` if you want it to stick.

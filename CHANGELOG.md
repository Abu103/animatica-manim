# Changelog

## Unreleased
- Fix: `animatica make --debug` now prints the validation errors before the traceback when storyboard generation fails. It used to show only "failed to fill 1 scene(s) after retries" with no reason.
- New: with `--narrate`, the model is asked to write a separate spoken `narration` per beat (T34b): a short caption on screen, 1 to 3 sentences for the voice that add the why or an intuition, written for the ear (no symbols, math in words, at most 250 characters). Both generation modes (one-stage, two-stage fill) do it; without `--narrate` the prompt is unchanged. Narrated storyboards cache under their own key, so a plain run never resumes one.
- New: lint checks the spoken line (T34c). Narration that describes the production ("this scene shows...") is dropped and the caption is spoken instead; narration with symbols a voice would read literally (`^`, `=`, `_`...), over 250 characters, or mentioning a ball on a component that draws none only warns. Hand-written `--from` storyboards are never touched.
- New: a beat can carry its own `narration` (T34). `--narrate` speaks it instead of the caption; blank keeps the old behaviour (read the caption), so existing storyboards render the same. The burned-in caption and `captions.vtt` still show the caption.
- Improve: `skills/animatica/SKILL.md` now follows the section layout Hermes' skill guide recommends (When to Use, Pitfalls, Verification) and says which parts need a repo checkout, so it reads correctly when installed from a hub with no repo around it.
- Improve: the MCP server (`animatica mcp`) is easier for an agent to drive. New `lint_storyboard` tool; `render_storyboard` takes `narrate` and `voice`; `validate_storyboard` reports an unreadable or malformed storyboard as a `load error:` entry (like the CLI) instead of a failed tool call; `component_schema` lists the valid names on an unknown one. `skills/animatica/SKILL.md` gains the frontmatter the repo's other skill uses, and a test fails if it stops naming a tool the server exposes.
- New: `unit_circle` component (T32): 1-4 special angles marked on the unit circle with their exact (cos, sin) such as (√3/2, 1/2), labelled in degrees or radians. Angles are multiples of 30 or 45 degrees so every value is exact; the values are looked up, never typed in. Duration 2.5 s + 0.9 s per angle.
- New: `graph_traversal` component (T31): a small graph walked breadth-first or depth-first from a start node, optionally directed. The visit order is computed (neighbours in `nodes` order), not typed in, so it is always correct; unreachable nodes stay dim. Duration 2.5 s + 0.6 s per visited node.
- New: `code_diff` component (T30): shows what changes between two versions of a snippet, removed lines red and added lines green, unchanged lines dimmed for context. Give the full `before` and `after`; the diff is computed, so it is always correct, and indentation is kept. Duration 2.5 s + 0.5 s per changed line.
- New: `pie_donut` component (T29): a pie or donut chart of 2-6 slices, each labelled with its share as whole-number percents that always add up to 100. `donut: true` cuts a hole that can hold a short `center` text. Slices under 3% are rejected with advice to merge them into "Other". Duration 2.0 s + 0.5 s per slice.
- New: `venn` component (T28): two or three overlapping sets with items in each set and in the shared regions (`shared: [{of: [0, 1], items: [...]}]`). Region sizes are validated, since three circles leave small regions. Duration 2.0 s + 0.7 s per set + 0.5 s per shared region.
- New: `probability_tree` component (T27): a root, up to 3 branches with up to 3 sub-branches each, every edge labelled with its probability, and the probability of each whole path at the end. Sibling probabilities must sum to 1 (checked, with the branch named in the error). Duration 2.0 s + 0.5 s per node.
- Fix: captions that describe the production instead of teaching ("Two columns contrast...", "A statistic callout...", "Show final distances...") are now all reported, not just "title card" ones: `--narrate` speaks the caption, so they were audible. A `title_card` whose caption describes the card is captioned (and narrated) with its own title by the lint pass.
- Fix: `--narrate` on Windows/macOS no longer runs the Linux Piper binary (`OSError: [WinError 193]`). Off Linux, `animatica doctor --fix` / the first `--narrate` pip-installs `piper-tts` (the maintained OHF-Voice/piper1-gpl engine, **GPL-3.0-or-later**; run as a separate process) and uses the `piper` entry point pip puts next to the interpreter; a Linux binary left in the narration cache by an older version is ignored off Linux. Linux still uses the sha256-pinned rhasspy/piper v1.2.0 binary (MIT).
- Fix: NIM replies cut off by the token limit (a reasoning model spending all of `max_tokens` thinking) no longer fail the two-stage run: `max_tokens` 4096 -> 16384, thinking off by default (`ANIMATICA_NIM_THINKING=1` turns it on), and the one retry doubles `max_tokens` (cap 32768) instead of resending the same request.
- Fix: `array_viz` draws `inf` as `∞`, and the lint pass rewrites a 9999+ placeholder (e.g. `999999`) to `"inf"` when the beat's own caption or title says infinity. A real out-2 render showed `999999` boxes under a caption saying "infinity".
- Fix: HyperFrames backend: a render timeout or a CLI that cannot be started (e.g. WinError 193) is a readable error, `capabilities()` honours `ANIMATICA_HYPERFRAMES`, the template's glows/masthead/footer no longer trip frame-lint (25 warnings on a real Windows render), DejaVu Sans is bundled (Bitstream Vera licence file included) so the render matches the planner's glyph widths on every machine, and `Encoder:` no longer claims x264 for a non-Manim backend.

## v0.2.0 (2026-11-14)
- New: one-command sandbox setup, `scripts/sandbox.sh`: a bare machine (curl, tar, sh) to a verified checkout, with `animatica doctor` and a smoke render. The prebuilt runtime is published by `.github/workflows/sandbox-runtime.yml` and keyed by a hash of the dependency list (`scripts/runtime_key.sh`). Plan and spec: `docs/superpowers/` (PR #44).
- New: lint gate, `ruff` rules F and E9 in CI (`python -m ruff check src scripts tests`), with the 110 defects it found fixed. Four `test_pipeline` tests had patched a name production code no longer reads; they now patch `animatica.backends.ManimBackend`.
- Fix: a system `ffmpeg` no longer inherits the bundled cairo/pango directory on `LD_LIBRARY_PATH`, which made it die with a symbol lookup error (exit 127) and failed the concat step of a multi-scene render in the sandbox. `animatica._nativelibs.system_tool_env()` is used by every ffmpeg call.
- Fix: captions leave their room in every component, one `Text` per line (#35, #37, #43); `compare` layout aligned and margin-safe (#15, #16); graph legend, tick labels and plot size against the real caption (#26); `parametric_graph` uses equal axis scales.
- CI: Linux job split into tests and render with a persisted render cache (#36); apt downloads cached; real-render gate with zero skips allowed on Linux and Windows (#17, #46).
- New: `--model` and `provider:model` for `animatica eval`; eval baseline and reference corpus (#34).
- New: `animatica eval --save-dir DIR` writes each prompt's raw model responses, failure reasons and storyboard as one JSON file, so a live run can be replayed offline (groundwork for T17).
- New: offline regression gate (`tests/test_eval_gate.py`, T17): ten recorded NIM storyboards are replayed through parse, validate, lint and duration with no network, against `tests/fixtures/eval_replay/thresholds.json`.
- New: `scripts/render_gallery.py` renders every `docs/gallery/*.json` at preview quality, prints a table with warnings verbatim, exits non-zero if any render fails, and `--write-doc` pastes the run into `docs/GALLERY.md` (T18). New `docs/VERIFIED_INSTALLS.md`, empty until a real clean-machine run is reported (T19). README gets a "What you get" section (T20).
- Fix: the guidance rule for comparisons matches whole words ("the two before it" is not a comparison) and counts a `stat_callout` delta as a visual comparison; `fibonacci.json` and `stat_callout.json` no longer draw a false warning.
- Fix: `animatica eval` no longer dies on a network error. A request that gets no answer (DNS failure, refused connection, timeout) raises `ProviderUnreachable`; eval records it as a failed prompt and carries on, and any other provider error (a missing key, say) ends the run with one `Error:` line instead of a traceback.
- Fix: `code_walkthrough` and `code_highlight` accept `code` whose newlines arrive double-escaped (a literal backslash-n, so a three-line function looked like one line and every `lines` entry looked out of range). It is converted only when the string has no real newline. This was the cause of the flaky "explain this python function line by line" eval prompt: 2 of 4 live NIM runs failed on it, run 1 in `code_walkthrough` and run 3 in `code_highlight`.
- Fix: a chat reply with no text (`message.content` null: a reasoning model out of `max_tokens`, or a filtered answer) is retried once inside the groq, nim and openrouter providers, then raises `EmptyCompletion` with the `finish_reason` instead of a bare "got NoneType" parse error. `animatica eval` records that as a failed prompt and goes on. A live NIM run of "explain this python function line by line" failed this way in 1 of 4 runs.
- Fix: `code_walkthrough` leaves room for its closing fade-out, so a beat is no longer 0.4s longer than its declared duration.
- Fix: `extract_json` ignores brackets inside strings and finishes an object a model left one or more closing brackets short (a recorded NIM run for "derive the quadratic formula" failed on this); a cut-off reply now says so.
- Fix: the prompt catalog spells out the keys for `compare` (`heading`, `bullets`), `timeline` (`label`, `text`) and `array_viz`; models had been guessing `name`/`purpose` and `year`/`event`. A test fails if a component with free-form dict params has no hint.
- Fix: the Windows TinyTeX cache was keyed to the repo's `.tex`, but `scripts/bootstrap.ps1` unpacks the bundle into `%LOCALAPPDATA%\Animatica\tex`, so the job had been caching an empty directory every run (#50).
- CI: `windows` split into `windows-tests` and `windows-render`, run in parallel, with a cheap aggregate job judging both (same shape as the existing `linux`/`linux-tests`/`linux-render` split); fixes the windows job bottlenecking every CI run at over 4 minutes (#51).

## v0.1.1 (2026-11-04)
- Release asset: `tinytex-manim.zip` (sha256 83fde080e52cdd7209738fb0876e3ddd3d5f755c5fdea4e2bca4222d120ecbf8), the pre-baked TinyTeX tree used by `scripts/bootstrap.{sh,ps1}`.
- Note: this tag was cut while the source tree still said `0.1.0`, so the published `animatica --version` reported 0.1.0. Fixed after the fact in 0.2.0.dev0 (see `tests/test_version.py`).

- Setup: parallel `scripts/bootstrap.{sh,ps1}` (~25-40s full quality) using `uv` + pre-baked TinyTeX release zip; ffmpeg now comes from the `imageio-ffmpeg` bundled binary when no system ffmpeg exists (doctor + encoder probe). CI workflow `build-tinytex.yml` bakes the zip.
- New: `animatica bootstrap` one-command setup; `animatica doctor --fix` now auto-installs ffmpeg and TinyTeX + required TeX packages (standalone preview babel-english amsmath amsfonts dvisvgm).
- New: `table` component (max 6x6, rows fade in one by one) -- task card T4.
- New: `number_line` component (line, ticks, jumping arrows) -- task card T1.
- New: `animatica eval` -- deterministic eval harness over reference prompts (P1.2).
- New: `--two-stage` on `animatica make` -- P1.1 two-stage generation (scene outline, then params filled per scene with individual retries).
- New: `animatica new-component NAME` scaffolds a component (module, registry entry, COMPONENTS.md row, test, conformance JSON) -- task card T9 for Hermes/Nemotron.
- New: `skills/animatica/SKILL.md` agent guide for the Hermes handoff.
- New: `scale` (auto/linear/sqrt/log) on `bounce_sequence` and `bar_chart`; auto mode keeps small values visible (Fibonacci 0..15). A small on-screen note says when height is not linear.
- Change: `bounce_sequence` holds up to 20 terms; prompt tells the model never to split a sequence.
- New: `storyboard/lint.py` cleans model-written storyboards (merges split sequences, drops repeat charts, warns about captions that mention a ball nothing draws). Not applied to `--from` files.
- Change: `doctor` tips when no AI provider is set; setup wizard lists where to get free keys; README rewritten; `docs/gallery/` added.
- Fix: LaTeX failures no longer show raw source. Equations fall back to readable text (real sub/superscripts, one line per equation) and the warning names the missing TeX package and the fix.
- Fix: `animatica doctor` now compiles a test formula, so a broken TeX install (e.g. missing `standalone.cls`) is reported instead of "all passed".
- Fix: diagram was drawn off-centre and clipped; labels/arrows now legible. Diagram and equation-transform durations now match what they declare (captions no longer drift).
- Fix: graph keeps its curve (without tick numbers) when LaTeX fails; code block scaled up to be readable.
- Fix: explicit `--provider X` skips offline templates; template keywords match whole words only.
- Fix: `--preview` honoured; warnings printed in the terminal, not only in report.json.
- New: `bounce_sequence` component (ball hops along a number sequence, pad height = value, running sum shown). LLM prompt updated to use it and to caption only what is drawn.
- New: burned-in captions (`--no-captions` to disable).
- Initial scaffold, config, CLI skeleton.
- Fix: AI providers now receive full storyboard instructions (format, limits, component catalog, example) via `ai/prompt.py`; previously only the bare user prompt was sent, so every non-template prompt failed with `StoryboardGenerationError`.
- Fix: retry feedback keeps the instructions and names the exact fields that failed.
- Fix: `animatica make` prints validation / provider / rate-limit errors instead of a traceback (`--debug` still shows it).
- Fix: `--provider template` gives a clear message; cloud calls set `max_tokens=4096`; AI storyboards are cached per prompt+provider.
- Fix: multi-scene videos failed to join with a relative `-o` dir / Windows paths (ffmpeg concat list now uses absolute forward-slash paths); ffmpeg stderr is surfaced on failure. `--model` / `ANIMATICA_MODEL` override; NIM default model updated.

## Unreleased
- New: prebuilt Windows LaTeX bundle (task card T12). `.github/workflows/build-tinytex-windows.yml` builds TinyTeX on `windows-latest` and publishes `tinytex-manim-win.zip`; `animatica doctor --fix` on Windows tries it first, verified against a pinned sha256, and falls back to the upstream TinyTeX installer. The bundle fails closed: it is not downloaded at all while its expected hash is unknown.
- Fix/F5-F7: stabilize renderer (F1-F4) and wire the backend seam (`--backend`, `--jobs`, single `report.json` writer); cache key now covers model + two-stage mode + registry fingerprint.
- New: `--jobs` scene parallelism via threads (`render_scenes_parallel`); default stays `1` (timings: jobs 1 = 13.8s, jobs 4 = 15.8s on the fibonacci gallery — no gain at small scale, per spec 16.3).
- Fix: `array_viz` swap moves both boxes simultaneously from original centers (was overlapping); `low`/`high`/`mid` now draw.
- Fix: graph labels typeset as math with plain-text fallback when LaTeX is missing.
- Fix: `--backend nope` exits non-zero listing valid names; `report.json` records backend name/version; `ManimBackend` no longer writes `report.json` (single writer in `make_video`).
- Fix: `ProcessPoolExecutor` -> `ThreadPoolExecutor`; removes the `fork()` deprecation warnings; closures no longer need to be picklable.
- Fix: `doctor --fix` repairs a TeX that is installed but incomplete (kpsewhich shows a needed file missing) and leaves a healthy one untouched.
- Fix: GPU detection falls back to `Get-CimInstance` when `wmic` is gone (Windows 11 24H2+); one missing tool no longer hides the others; `probe_encoders(platform=)` is injectable so Linux CI can test Windows/macOS paths.
- Change: NIM default model is `nvidia/nemotron-3.5-super-vl-120b-a12b` (code + providers.toml).
- Docs: `docs/COMPONENTS.md` TODO rows replaced with real params; tests now fail if the doc drifts from the registry.
- Docs: README no longer promises a 25-40s install.
- New: agent JSON-CLI tools `list-components`, `component-schema`, `validate`, `lint` (P2, Hermes can drive these directly).
- New: `array_viz`, `timeline`, `compare` components -- task cards T3, T5, T6.
- New: `recursion_tree` component (Fibonacci call tree, repeated calls in red, 31-node cap) -- task card T2.

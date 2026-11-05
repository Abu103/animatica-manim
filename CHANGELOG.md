# Changelog

## Unreleased
- Fix: `doctor --fix` repairs a TeX that is installed but incomplete (kpsewhich shows a needed file missing) and leaves a healthy one untouched.
- Fix: GPU detection falls back to `Get-CimInstance` when `wmic` is gone (Windows 11 24H2+); one missing tool no longer hides the others; `probe_encoders(platform=)` is injectable so Linux CI can test Windows/macOS paths.
- Change: NIM default model is `nvidia/nemotron-3.5-super-vl-120b-a12b` (code + providers.toml).
- Docs: `docs/COMPONENTS.md` TODO rows replaced with real params; tests now fail if the doc drifts from the registry.
- Docs: README no longer promises a 25-40s install.
- New: agent JSON-CLI tools `list-components`, `component-schema`, `validate`, `lint` (P2, Hermes can drive these directly).
- New: `array_viz`, `timeline`, `compare` components -- task cards T3, T5, T6.
- New: `recursion_tree` component (Fibonacci call tree, repeated calls in red, 31-node cap) -- task card T2.
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


# Changelog

## v0.1.1 (2026-11-04)
- Release asset: `tinytex-manim.zip` (sha256 83fde080e52cdd7209738fb0876e3ddd3d5f755c5fdea4e2bca4222d120ecbf8), the pre-baked TinyTeX tree used by `scripts/bootstrap.{sh,ps1}`.
- Note: this tag was cut while the source tree still said `0.1.0`, so the published `animatica --version` reported 0.1.0. Fixed after the fact in 0.2.0.dev0 (see `tests/test_version.py`).

- Setup: parallel `scripts/bootstrap.{sh,ps1}` (~25-40s full quality) using `uv` + pre-baked TinyTeX release zip; ffmpeg now comes from the `imageio-ffmpeg` bundled binary when no system ffmpeg exists (doctor + encoder probe). CI workflow `build-tinytex.yml` bakes the zip.
- New: `animatica bootstrap` one-command setup; `animatica doctor --fix` now auto-installs ffmpeg and TinyTeX + required TeX packages (standalone preview babel-english amsmath amsfonts dvisvgm).
- New: `table` component (max 6x6, rows fade in one by one) -- task card T4.
- New: `number_line` component (line, ticks, jumping arrows) -- task card T1.
- New: `animatica eval --save-dir DIR` writes each prompt's raw model responses, failure reasons and storyboard as one JSON file, so a live run can be replayed offline (groundwork for T17).
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

# Animatica v1 — Prompt-to-Explainer CLI on Manim (Design Spec)

Date: 2026-11-04 · Status: draft for review · Path: architectural

## 1. Goal and success criteria

One command turns a plain-language prompt into a 3Blue1Brown-style explainer
video (MP4 + captions) with no Python or LaTeX knowledge from the user, using
as little LLM as possible and only free-tier providers.

```
animatica make "explain the pythagorean theorem a^2 + b^2 = c^2" -o out/
```

v1 is done when:
1. A user who has never opened a terminal can follow `docs/GUIDE.md` and render
   their first video on Windows, macOS or Linux.
2. 80% of a fixed set of 30 reference prompts render without error on a free
   tier model; the 10 most common ones render with the LLM disabled (templates).
3. Output uses real LaTeX math, axes/graphs, morphs and draw-on animation.
4. `doctor` reports every missing dependency with an exact fix.
5. The hardware encoder is auto-selected and verified, with x264 fallback.

## 2. Non-goals (v1)

Rust code in v1 (the seams for it ARE in scope, see section 16), dual Rust/Python validation, GPU rendering, voiceover, web UI,
physics engine, 3D, user-authored components, cloud rendering. Physics may
return later as an analytic component (ODE solved in Python), not an engine.

## 3. Users and constraints

Non-technical and low-budget users. No paid API keys. Works offline for
template prompts. CPU-only rendering (Manim Cairo renderer). Python 3.10+.

## 4. Architecture

```
prompt
  -> cache lookup (hash of prompt+provider+schema version)
  -> template matcher (offline)  --hit-->  Storyboard
  -> else LLM provider (1 call, JSON out, <=2 repair retries) -> Storyboard
  -> validate (Pydantic + safety checks)
  -> render: static scene file reads storyboard.json, calls component library
  -> Manim subprocess (preview or final quality)
  -> encode stage (hardware probe, optional transcode) -> out.mp4 + captions.vtt
```

Key rule: **the LLM never writes code, coordinates or timings.** It only picks
components and fills text/data. All layout, easing, timing and color live in
tested components. This is what lets small free models produce polished output.

Generated code never interpolates user/LLM strings. The scene file is static
and loads `storyboard.json` at runtime, so there is no code-injection surface.

## 5. Storyboard schema (Pydantic, versioned)

```json
{
  "version": "1",
  "title": "Pythagorean Theorem",
  "theme": {"palette": "dark-blue", "font": "default"},
  "scenes": [
    {"beats": [
      {"component": "title_card", "params": {"title": "Pythagorean Theorem"},
       "caption": "A relationship between the sides of a right triangle."},
      {"component": "equation", "params": {"mode": "reveal", "latex": ["a^2 + b^2 = c^2"]},
       "caption": "The squares of the legs add up to the square of the hypotenuse."}
    ]}
  ]
}
```

Limits: max 12 scenes, 8 beats per scene, 300 chars per text field, total
runtime cap 5 minutes (configurable). Unknown components are rejected and
reported to the repair loop.

## 6. Component library (v1: 8)

| Component | Params (summary) | Notes |
|---|---|---|
| title_card | title, subtitle | fade/write in |
| equation | mode reveal or transform, latex[] | real LaTeX; transform morphs step to step |
| graph | fn, x_range, y_range, label | axes, plotted curve, optional moving dot |
| bar_chart | labels[], values[], title | bars grow from a shared baseline, value labels |
| steps_list | items[] | sequential reveal with highlight |
| shape_morph | from, to, colors | circle/square/triangle/etc. |
| diagram | nodes[], edges[] | auto-layout, arrows draw on |
| code_highlight | code, language, lines[] | highlighted lines |

Each component: computes its own duration, reports it (used for captions),
auto-scales text to canvas, enforces minimum font size and WCAG AA contrast
against the theme background. New components are added by registering a class;
the LLM prompt and JSON schema are generated from the registry, so docs, schema
and validation cannot drift.

Function strings in `graph.fn` are parsed by a restricted expression parser
(allowlist: numbers, x, + - * / ^, sin cos tan exp log sqrt abs, pi, e). Never
`eval`.

## 7. LaTeX (required)

- LaTeX is a hard requirement, checked by `doctor`.
- Guided install: `animatica doctor --fix` offers TinyTeX (about 100 MB) on all
  three OSes and installs the packages Manim needs. Manual route is in the guide.
- Safety: LaTeX strings from the LLM are untrusted. Denylist `\write18`,
  `\input`, `\include`, `\openin`, `\openout`, `\immediate`, `\catcode`;
  shell-escape stays disabled; compile timeout per expression.
- A single bad LaTeX string degrades that beat to a plain text card and is
  reported; it does not abort the video.

## 8. AI providers

| Provider | Needs | Notes |
|---|---|---|
| template | nothing | offline; matches common prompt patterns |
| groq | key | free tier |
| openrouter | key | `:free` models only by default |
| nim | key | NVIDIA NIM free tier |
| ollama | local server | fully offline |

- `provider = auto` order: template, then the first configured provider.
- One call per video. JSON-schema/structured output where the provider supports
  it; otherwise JSON mode plus strict parsing. Repair loop feeds back at most
  the first 6 validation errors, max 2 retries.
- Cloud use is opt-in at `setup` time and the chosen provider is always printed.
- Prompts and keys: keys live in the user config dir, file mode 600, never in
  the project folder or logs.
- Free-tier rate limits and model names change often. They are not hardcoded:
  model names live in a small `providers.toml` users can edit, and rate-limit
  errors produce a clear "wait N seconds or switch provider" message.
  Current limits must be verified during implementation planning.

## 9. Encode stage and hardware acceleration

- ffmpeg is used as a subprocess (not PyAV): it uses the user's own build and
  encoders. Manim's own output is the source.
- Default (`--quality standard`): use Manim's x264 output directly, no second
  lossy encode.
- `--fast` or `--encoder auto`: transcode with a hardware encoder if one passes
  verification.
- Device detection: `nvidia-smi`, `vainfo`, Windows video-controller query,
  `system_profiler`.
- Candidate order: NVENC, QSV, VAAPI (Linux) / AMF (Windows), VideoToolbox
  (macOS), then libx264.
- Each candidate must pass a real test encode of a small clip; results are
  cached per machine and per ffmpeg build. Any failure falls back to x264
  with a one-line explanation. Output always states the encoder used.
- Honest default: x264 gives better quality per bit on flat graphics and
  rendering dominates time; hardware mode is the speed option.

## 10. CLI

```
animatica setup            # wizard: choose provider, paste key, run doctor
animatica doctor [--fix]   # check Python, Manim, LaTeX, ffmpeg, encoders, keys
animatica make "prompt"    # -o DIR  --preview  --quality  --encoder  --provider
animatica make --from storyboard.json   # skip AI, re-render or hand-edit
animatica templates        # list offline templates with example prompts
animatica guide            # print the beginner quick-start in the terminal
```

Every run saves `storyboard.json` next to the video, so users can tweak text
and re-render for free, and a future web UI can drive the same files.

## 11. Errors and degradation

- Beat-level failure becomes a text card plus a warning in the final report.
- Provider failure: retry per section 8, then suggest `--provider template` or
  another provider; never a raw stack trace (use `--debug` for those).
- Every error message names the cause and the exact next step.

## 12. Beginner guide (deliverable: `docs/GUIDE.md`)

Written for people who have never used a terminal. Sections:
1. What this does, with a sample video and prompt.
2. What you need (plain list, install time estimate).
3. Step-by-step install per OS: Windows (`py` launcher, winget for ffmpeg and
   Python, avoiding MSYS/Store Python mixups), macOS (brew), Linux (apt).
   Each step shows the exact command and the expected output.
4. Virtual environment explained in three sentences, with copy-paste commands.
5. Run `animatica doctor` and how to read each line.
6. Your first video, then how to see and replay it.
7. Writing good prompts: 10 examples that work, 5 that do not and why.
8. Getting a free API key for Groq, OpenRouter and NIM, step by step.
9. Editing `storyboard.json` to fix a typo without any AI.
10. Troubleshooting table keyed by the exact error text.
11. Glossary: terminal, PATH, virtual environment, API key, LaTeX, encoder.

`animatica guide` and `setup` reuse this content so the terminal and the doc
cannot disagree.

## 13. Repository layout

```
animatica/
  pyproject.toml
  src/animatica/
    cli.py  setup.py  doctor.py  config.py
    storyboard/ models.py  safety.py  cache.py
    ai/ base.py  router.py  template.py  groq.py  openrouter.py  nim.py  ollama.py  providers.toml
    components/ registry.py  title_card.py  equation.py  graph.py  bar_chart.py
                steps_list.py  shape_morph.py  diagram.py  code_highlight.py  theme.py
    backends/ base.py (RenderBackend protocol)  manim_backend.py  scheduler.py
    native/ __init__.py (optional animatica-native loader, pure-Python fallbacks)
    encode/ probe.py  transcode.py
    plugins.py (entry-point loader)  report.py (per-stage timing)
  rust/ README.md only in v1: contract, build notes, no code
  tests/ conformance/ (shared corpus any backend must pass)
  docs/ GUIDE.md  COMPONENTS.md  superpowers/specs/
```

Migration from the current repo: keep the template-matching idea, provider
router shape and accessibility contrast math (ported); delete the Rust
workspace, the physics scenes, the generated `out_*` folders and the Pydantic
IR in favor of the storyboard schema. Do this in a fresh branch or folder so
the old work stays recoverable (the current folder has no git history).

## 14. Testing

- Unit: storyboard validation, safety denylist, function parser, cache keys,
  provider router, encoder-probe parsing with mocked ffmpeg and device output.
- Determinism: same storyboard produces an identical generated manifest.
- Component smoke tests: each component renders at 480p15 in CI.
- Golden check: 3 frames per component compared by structural similarity.
- Reference prompt suite (30): template path runs in CI with no network;
  LLM path is a manual, opt-in script.
- CI runs Ubuntu, macOS and Windows with TinyTeX installed.

## 15. Assumptions and risks

- Assumes Manim Community (version pinned in `pyproject.toml`) is the renderer.
  Manim API changes are the main upgrade risk, contained to `components/`.
- Free-tier models will sometimes produce weak storyboards. Mitigation:
  constrained schema, templates first, repair loop, and editable
  `storyboard.json`.
- Install friction (Cairo, Pango, LaTeX, ffmpeg) is the biggest adoption risk,
  which is why `doctor --fix`, `setup` and the guide are v1 scope, not extras.
- Name collision: "Animatica" is used by other software. Check PyPI and trademark
  before publishing.

## 16. Modularity, scale and the Rust seam

Principle: the **storyboard JSON is the stable contract**. Everything left of
it (prompt, templates, LLM) and right of it (rendering, encoding) can be
replaced independently. Rust, if and when it is justified, plugs in right of
the contract, not through the middle of the Python code.

### 16.1 Extension points (all via a registry + Python entry points)

| Group | Interface | v1 implementations |
|---|---|---|
| `animatica.components` | `Component` (params model, build, duration) | the 8 in section 6 |
| `animatica.providers` | `AIProvider.generate(prompt, schema) -> str` | template, groq, openrouter, nim, ollama |
| `animatica.backends` | `RenderBackend.render(storyboard, opts) -> RenderResult` | `manim` |
| `animatica.encoders` | `Encoder` (probe, args) | x264, nvenc, qsv, vaapi, amf, videotoolbox |
| `animatica.templates` | `Template.match(prompt) -> Storyboard or None` | built-in set |

Third parties (or a future `animatica-native` wheel) register through entry
points without touching core. Core never imports a concrete implementation by
name outside its own registration module.

### 16.2 Rust-ready seams (nothing built, interfaces fixed now)

1. **Render backend.** A Rust backend would be a second `RenderBackend` that
   consumes the same `storyboard.json` and returns the same `RenderResult`
   (frame dir or video path + durations). Integration options, decided at that
   time by measurement: a subprocess binary (simplest, like the old
   `animatica-engine`) or a PyO3 module built with maturin.
2. **Hot numeric helpers.** Narrow pure functions in `native/` with Python
   fallbacks: `sample_function(fn, x_range, n)`, `layout_graph(nodes, edges)`,
   `bezier_resample(path, n)`. If `animatica-native` is installed these use
   Rust; otherwise the pure-Python versions run. Same signatures, same tests.
3. **Parallelism.** `scheduler.py` renders independent scenes in a process
   pool and concatenates clips with ffmpeg. Schema rule that enables it: each
   scene starts from a clean canvas and shares no state. This delivers most of
   the multi-core win without Rust.
4. **Conformance corpus.** `tests/conformance/` holds storyboards plus expected
   outputs (durations, frame counts, structural checks). Any backend, Python or
   Rust, must pass the same corpus before it can be selected.
5. **Optional packaging.** `animatica-native` is a separate optional wheel.
   Missing wheel is never an error; `doctor` just reports "native: not
   installed (pure Python in use)".

### 16.3 Measure before porting

Every run writes `report.json` with per-stage wall time: LLM, LaTeX compile,
frame drawing, encode, total. `animatica bench` runs the reference prompts and
prints a stage table. The rule for starting any Rust work: the stage it
replaces must exceed 40% of total render time on the reference suite, and the
conformance corpus must exist for it first.

### 16.4 Versioning and maintenance

- Storyboard schema carries `version`; loaders run explicit migrations from
  older versions, never silent field guessing.
- Each component declares `api_version`; the registry refuses mismatched
  plugins with a clear message.
- Core follows semver; the plugin interfaces above are the public API.
- Manim is pinned and touched only inside `components/` and
  `backends/manim_backend.py`, so a Manim upgrade is a contained change.
- `CHANGELOG.md`, deprecation warnings for one minor version before removal,
  and CI on Ubuntu/macOS/Windows keep updates safe.
- Adding a feature should mean adding one file and one registry entry:
  new component, provider, encoder or backend.


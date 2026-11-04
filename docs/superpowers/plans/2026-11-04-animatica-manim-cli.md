# Animatica v1 (Manim CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI that turns a plain-language prompt into a Manim-rendered explainer video (MP4 + captions), using templates first and at most one free-tier LLM call.

**Architecture:** Prompt -> template or LLM -> validated `Storyboard` JSON (the stable contract) -> backend-agnostic `RenderBackend` (Manim in v1, scene-parallel) -> encode stage with verified hardware probing. Components, providers, backends, encoders and templates register through Python entry points so features are added as one file plus one registry entry.

**Tech Stack:** Python 3.10+, Manim Community (pinned), Pydantic v2, Typer, httpx, pytest, ffmpeg (subprocess), TinyTeX/LaTeX.

**Spec:** `docs/superpowers/specs/2026-11-04-animatica-manim-cli-design.md` (read it first; section numbers below refer to it).

**Project root:** a NEW folder `animatica-v1/` (old Rust-based repo is left untouched). Copy the spec and this plan into `animatica-v1/docs/superpowers/` in Task 1.

## Global Constraints

- Python 3.10+; CPU-only rendering (Manim Cairo renderer); no GPU render libs.
- Storyboard limits: max 12 scenes, 8 beats per scene, 300 chars per text field, total runtime cap 5 minutes (configurable).
- LLM never writes code, coordinates or timings; generated scene file never interpolates LLM/user strings (static scene reads `storyboard.json`).
- One LLM call per video; repair loop feeds back the first 6 validation errors, max 2 retries; `auto` provider order: template, then first configured provider.
- Providers: `template`, `groq`, `openrouter` (`:free` models only by default), `nim`, `ollama`. Cloud is opt-in at `setup`; chosen provider always printed. Model names live in editable `providers.toml`.
- API keys stored in the user config dir, file mode 600, never in project folder or logs.
- LaTeX required. Denylist in LaTeX strings: `\write18`, `\input`, `\include`, `\openin`, `\openout`, `\immediate`, `\catcode`; shell-escape disabled; per-expression compile timeout.
- `graph.fn` parsed by restricted parser, allowlist: numbers, `x`, `+ - * / ^`, `sin cos tan exp log sqrt abs`, `pi`, `e`. Never `eval`.
- ffmpeg used as a subprocess, not PyAV. Encoder order: NVENC, QSV, VAAPI (Linux) / AMF (Windows), VideoToolbox (macOS), libx264. Every hardware candidate must pass a real test encode; results cached per machine and ffmpeg build; any failure falls back to x264 and prints encoder used and why. Default quality mode uses Manim's x264 output directly (no second lossy encode).
- Failure in one beat degrades to a plain text card plus warning; never aborts the video. Errors name cause and exact next step; raw stack traces only with `--debug`.
- Manim is pinned (`==`) and imported only inside `components/` and `backends/manim_backend.py`.
- Execution environment: tests that need Manim/LaTeX carry `@pytest.mark.render` and are skipped when those are missing; all other tests must pass without them.
- Contrast: WCAG AA (4.5:1) against theme background; minimum font size enforced by components.

## Review Focus

1. LLM reply is JSON wrapped in markdown fences or surrounded by prose -> still parsed (Task 12).
2. Output dir or prompt contains spaces, unicode or Windows-style paths -> renders and writes files correctly (Task 15).
3. A LaTeX string with unbalanced braces or compile error -> that beat becomes a text card with a warning, video still finishes (Task 6).
4. `graph.fn` hits singularities (`tan(x)`, `1/x` at 0, `log` of negatives) -> gaps in the curve, no crash, no NaN lines (Task 7).
5. Hardware encoder passes the probe but fails during the real transcode -> original Manim MP4 is kept and delivered, with a warning (Task 11).

---

### Task 1: Project scaffold, config, CLI skeleton

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/animatica/__init__.py`, `src/animatica/cli.py`, `src/animatica/config.py`, `tests/test_cli.py`, `tests/test_config.py`, `docs/superpowers/` (copy spec + plan), `CHANGELOG.md`
- Run once: `git init`

**Interfaces:**
- Produces: `animatica.cli.app` (Typer app, console script `animatica`); `animatica.config.Config` (dataclass: `provider: str="auto"`, `cloud_allowed: bool=False`, `max_runtime_secs: int=300`); `config_dir() -> Path`; `load_config() -> Config`; `save_config(Config) -> None`; `save_key(provider: str, key: str) -> None` (file mode 600); `load_key(provider: str) -> str | None`.

- [ ] **Step 1: Write failing tests**
  - `test_version`: `CliRunner().invoke(app, ["--version"])` exit 0, output contains `animatica`.
  - `test_config_roundtrip`: `save_config(Config(provider="groq"))` then `load_config().provider == "groq"` (use `monkeypatch.setenv("ANIMATICA_CONFIG_DIR", tmp_path)`).
  - `test_key_file_mode`: after `save_key("groq","k")`, `stat().st_mode & 0o777 == 0o600` (skip on Windows); `load_key("groq") == "k"`; key text absent from `config.toml`.
- [ ] **Step 2: Run** `pytest tests/test_cli.py tests/test_config.py -v` -> FAIL (module missing).
- [ ] **Step 3: Implement** the interfaces above; `pyproject.toml` with `manim==<latest stable on PyPI today>`, entry point group declarations empty for now; `ANIMATICA_CONFIG_DIR` overrides the platform default (`platformdirs`).
- [ ] **Step 4: Run** same command -> PASS; `pip install -e ".[dev]"` succeeds.
- [ ] **Step 5: Commit** `git add -A && git commit -m "chore: scaffold animatica-v1 with config and CLI skeleton"`

### Task 2: Storyboard models, limits, migrations

**Files:**
- Create: `src/animatica/storyboard/__init__.py`, `src/animatica/storyboard/models.py`, `tests/test_storyboard_models.py`

**Interfaces:**
- Produces: `Theme(palette: str="dark-blue", font: str="default")`; `Beat(component: str, params: dict[str, Any], caption: str="")`; `Scene(beats: list[Beat])`; `Storyboard(version: Literal["1"]="1", title: str, theme: Theme, scenes: list[Scene])`; `MAX_SCENES=12`, `MAX_BEATS=8`, `MAX_TEXT=300`; `migrate(data: dict) -> dict`; `load_storyboard(path: Path) -> Storyboard`; `dump_storyboard(sb, path) -> None`.

- [ ] **Step 1: Failing tests:** `test_valid_roundtrip` (spec section 5 example loads and dumps equal); `test_too_many_scenes` (13 scenes -> `ValidationError`); `test_too_many_beats` (9); `test_text_too_long` (caption 301 chars); `test_migrate_unknown_version_raises` (`version:"0"` -> `ValueError` naming supported versions); `test_empty_scenes_rejected`.
- [ ] **Step 2: Run** `pytest tests/test_storyboard_models.py -v` -> FAIL.
- [ ] **Step 3: Implement** per signatures; `migrate` is the only place version differences are handled (v1 is identity; unknown raises).
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: storyboard models with limits and migration hook`

### Task 3: Safety (LaTeX denylist, restricted function parser)

**Files:**
- Create: `src/animatica/storyboard/safety.py`, `tests/test_safety.py`

**Interfaces:**
- Produces: `class UnsafeInput(ValueError)`; `check_latex(s: str) -> None` (raises `UnsafeInput` on any denylisted control sequence, case-sensitive match on the backslash form, also rejects strings over `MAX_TEXT`); `parse_function(expr: str) -> Callable[[float], float]` (raises `UnsafeInput` on anything outside the allowlist).

- [ ] **Step 1: Failing tests:** `check_latex(r"a^2+b^2=c^2")` passes; each of `\write18`, `\input`, `\include`, `\openin`, `\openout`, `\immediate`, `\catcode` raises; `parse_function("sin(x)^2 + 1/2")(0.0) == 0.5`; `parse_function("x^2")(3) == 9`; `parse_function("__import__('os')")` raises; `parse_function("x.real")` raises; `parse_function("open('f')")` raises; `parse_function("2x")` raises `UnsafeInput` (no implicit multiplication).
- [ ] **Step 2: Run** `pytest tests/test_safety.py -v` -> FAIL.
- [ ] **Step 3: Implement** `parse_function` by walking `ast.parse(expr.replace("^","**"), mode="eval")` and permitting only `BinOp`, `UnaryOp`, `Constant(int|float)`, `Name` in `{x, pi, e}`, and `Call` of allowlisted function names.
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: LaTeX denylist and restricted function parser`

### Task 4: Plugin registry and component base

**Files:**
- Create: `src/animatica/plugins.py`, `src/animatica/components/__init__.py`, `src/animatica/components/base.py`, `src/animatica/components/registry.py`, `tests/test_registry.py`

**Interfaces:**
- Consumes: `Storyboard`, `Beat` (Task 2).
- Produces: `load_entry_points(group: str) -> dict[str, Any]`; `class Component(ABC)` with `name: ClassVar[str]`, `api_version: ClassVar[int] = 1`, `Params: ClassVar[type[BaseModel]]`, `duration(self, p: BaseModel) -> float`, `play(self, scene: "manim.Scene", p: BaseModel, colors: "ThemeColors") -> None`, `fallback_text(self, p: BaseModel) -> str`; `class ComponentRegistry` with `register(cls)`, `get(name) -> Component`, `names() -> list[str]`, `json_schema() -> dict` (generated from all `Params`), `validate(sb: Storyboard) -> list[str]` (human-readable errors, unknown component and bad params included); `default_registry() -> ComponentRegistry` (built-ins + entry point group `animatica.components`). Registry refuses `api_version != 1` with a clear message.

- [ ] **Step 1: Failing tests:** register a fake component; `validate` returns `[]` for a good beat; unknown component -> error string contains the name and lists valid names; bad params -> error contains the field name; `json_schema()` has one entry per registered component; fake plugin with `api_version=2` rejected; `load_entry_points` returns `{}` for an empty group.
- [ ] **Step 2: Run** `pytest tests/test_registry.py -v` -> FAIL.
- [ ] **Step 3: Implement** with `importlib.metadata.entry_points(group=...)`.
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: plugin registry and component base`

### Task 5: Theme and accessibility

**Files:**
- Create: `src/animatica/components/theme.py`, `tests/test_theme.py`

**Interfaces:**
- Produces: `ThemeColors(background: str, text: str, accent: str, accent2: str, muted: str)`; `PALETTES: dict[str, ThemeColors]` (at least `dark-blue`, `light`, `high-contrast`); `get_colors(theme: Theme) -> ThemeColors` (unknown palette -> `ValueError` listing valid ones); `contrast_ratio(fg: str, bg: str) -> float` (WCAG formula); `MIN_FONT_PX = 32` at 1080p height (3% of frame height).

- [ ] **Step 1: Failing tests:** `contrast_ratio("#000000","#FFFFFF") == pytest.approx(21.0)`; same color -> 1.0; every palette's `text`, `accent`, `accent2` vs `background` >= 4.5; unknown palette raises.
- [ ] **Step 2: Run** `pytest tests/test_theme.py -v` -> FAIL.
- [ ] **Step 3: Implement** with sRGB-to-linear luminance.
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: themes with WCAG contrast checks`

### Task 6: Components batch 1 — title_card, equation, steps_list

**Files:**
- Create: `src/animatica/components/title_card.py`, `equation.py`, `steps_list.py`; Test: `tests/test_components_text.py`; Modify: `components/registry.py` (register built-ins)

**Interfaces:**
- Consumes: `Component`, `check_latex`, `ThemeColors`.
- Produces: `title_card` Params `{title: str, subtitle: str=""}`; `equation` Params `{mode: Literal["reveal","transform"]="reveal", latex: list[str] (1..6)}`; `steps_list` Params `{items: list[str] (1..8)}`. Each `duration(p)` is a pure function of params (title 3.0s; equation 2.0s + 2.0s per extra step; steps_list 1.5s per item + 1.0s). Each `play` degrades per Global Constraints: a LaTeX compile failure inside `equation.play` renders `fallback_text` in a text card and appends a warning to `scene.warnings`.

- [ ] **Step 1: Failing tests (no Manim):** durations equal the formulas above; `equation` rejects an unsafe latex string at Params validation; empty `latex` list rejected. Tests with `@pytest.mark.render`: each component's `play` runs on a real `manim.Scene` at 480p15 and adds >= 1 mobject; `equation` with `r"\frac{a}{"` (unbalanced) does not raise and records one warning.
- [ ] **Step 2: Run** `pytest tests/test_components_text.py -v` -> FAIL.
- [ ] **Step 3: Implement** the three components; font sizes never below `MIN_FONT_PX`-equivalent in Manim units; text auto-scales to fit frame width.
- [ ] **Step 4: Run** -> PASS (render tests skip if Manim/LaTeX absent).
- [ ] **Step 5: Commit** `feat: title_card, equation, steps_list components`

### Task 7: Components batch 2 — graph, bar_chart (and native sampler seam)

**Files:**
- Create: `src/animatica/native/__init__.py`, `src/animatica/native/sampling.py`, `src/animatica/components/graph.py`, `bar_chart.py`; Test: `tests/test_sampling.py`, `tests/test_components_charts.py`

**Interfaces:**
- Produces: `native.sampling.sample_function(fn: Callable[[float], float], x_range: tuple[float, float], n: int) -> list[list[tuple[float, float]]]` (list of continuous segments; non-finite or jump-discontinuous points split segments; `native/__init__.py` exposes `sample_function` from `animatica_native` if importable, else this pure-Python one); `graph` Params `{fn: str, x_range: tuple[float,float], y_range: tuple[float,float], label: str=""}`; `bar_chart` Params `{title: str, labels: list[str], values: list[float]}` (1..12 bars, equal lengths, values >= 0); duration `graph` 4.0s, `bar_chart` 2.0s + 0.3s per bar.

- [ ] **Step 1: Failing tests:** `sample_function(lambda x: x*x, (0,2), 5)` -> one segment of 5 points ending at `(2.0, 4.0)`; `sample_function(lambda x: 1/x, (-1,1), 201)` returns >= 2 segments and no point with `abs(y) > 1e6`; `tan` over `(0, 2*pi)` splits at singularities; `log` over `(-1,1)` drops non-finite points; bar_chart rejects mismatched lengths and negative values; `@render` smoke tests for both.
- [ ] **Step 2: Run** -> FAIL.
- [ ] **Step 3: Implement.** Jump rule: split where `abs(y[i]-y[i-1]) > 0.5 * (y_max_range)` for consecutive samples; graph draws each segment as its own curve; clip to `y_range`.
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: graph and bar_chart components with sampling seam`

### Task 8: Components batch 3 — shape_morph, diagram, code_highlight (layout seam)

**Files:**
- Create: `src/animatica/native/layout.py`, `components/shape_morph.py`, `components/diagram.py`, `components/code_highlight.py`; Test: `tests/test_layout.py`, `tests/test_components_visual.py`

**Interfaces:**
- Produces: `native.layout.layout_graph(nodes: list[str], edges: list[tuple[str,str]], width: float, height: float) -> dict[str, tuple[float,float]]` (layered left-to-right layout; deterministic; exposed via `native/__init__.py` with the same native-or-fallback rule); `shape_morph` Params `{from_shape: Literal["circle","square","triangle","star"], to_shape: same, from_color: str=accent, to_color: str=accent2}`; `diagram` Params `{nodes: list[str] (2..10), edges: list[tuple[str,str]]}` (edges must reference nodes); `code_highlight` Params `{code: str (<=1200 chars), language: str="python", lines: list[int]=[]}`; durations 3.0s, 1.0s + 0.6s per edge, 3.0s + 1.0s per highlighted line.

- [ ] **Step 1: Failing tests:** layout is deterministic (two calls equal); every node inside `[0,width]x[0,height]`; no two nodes share a position; chain `a->b->c` has strictly increasing x; diagram rejects an edge to an unknown node; code_highlight rejects line numbers beyond the code's line count; `@render` smoke tests.
- [ ] **Step 2: Run** -> FAIL.
- [ ] **Step 3: Implement** (layer = longest-path depth; cycles broken by ignoring back edges).
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: shape_morph, diagram, code_highlight and layout seam`

### Task 9: Render backend, static scene, per-stage report

**Files:**
- Create: `src/animatica/backends/__init__.py`, `base.py`, `manim_backend.py`, `src/animatica/render/__init__.py`, `render/scene.py`, `src/animatica/report.py`; Test: `tests/test_backend_base.py`, `tests/test_backend_manim.py`

**Interfaces:**
- Consumes: `Storyboard`, `ComponentRegistry`, `get_colors`.
- Produces: `RenderOptions(quality: Literal["preview","standard","high"]="standard", jobs: int | None=None)`; `RenderResult(video: Path, durations: list[float], warnings: list[str], stage_times: dict[str, float])`; `class RenderBackend(Protocol)` with `name: str` and `render(sb: Storyboard, out_dir: Path, opts: RenderOptions) -> RenderResult`; `ManimBackend` registered under group `animatica.backends`; `render/scene.py` defines `StoryboardScene(manim.Scene)` that reads the path in env `ANIMATICA_STORYBOARD` and a scene index in `ANIMATICA_SCENE_INDEX`, plays that scene's beats via the registry, wrapping each beat in try/except that records a warning and shows `fallback_text`; `report.StageTimer` (context manager recording seconds per named stage) and `write_report(path, stage_times, warnings) -> None` writing `report.json`.
  Quality map: preview = 480p15, standard = 1080p30, high = 1080p60.

- [ ] **Step 1: Failing tests:** `StageTimer` records two stages summing to total; `write_report` produces JSON with keys `stages`, `warnings`; a fake backend satisfying the Protocol type-checks via `isinstance`-style runtime check (`runtime_checkable`); `@render`: `ManimBackend().render` on a 1-scene storyboard with `title_card` at preview quality creates an MP4 whose ffprobe duration is within 0.2s of the sum of reported `durations`; a beat whose component raises still yields a video plus one warning.
- [ ] **Step 2: Run** `pytest tests/test_backend_base.py tests/test_backend_manim.py -v` -> FAIL.
- [ ] **Step 3: Implement.** Manim is invoked as a subprocess (`python -m manim render <scene.py> StoryboardScene ...`) with storyboard path and scene index passed only via environment variables, never interpolated into code.
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: Manim render backend, static scene and stage report`

### Task 10: Scene-parallel scheduler

**Files:**
- Create: `src/animatica/backends/scheduler.py`; Modify: `backends/manim_backend.py`; Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `ManimBackend` single-scene render (Task 9).
- Produces: `render_scenes_parallel(render_one: Callable[[int], Path], n_scenes: int, jobs: int) -> list[Path]` (process pool, results in scene order, first failure cancels the rest and re-raises with the scene index); `concat_videos(clips: list[Path], dst: Path, ffmpeg: str="ffmpeg") -> None` (ffmpeg concat demuxer, `-c copy`); default `jobs = max(1, min(os.cpu_count() - 1, n_scenes))`.

- [ ] **Step 1: Failing tests:** with a fake `render_one` returning predictable paths, output order equals scene order even when later scenes finish first; an exception in scene 2 surfaces `"scene 2"` in the message; `jobs=1` runs serially; `concat_videos` builds the expected ffmpeg arg list (mock `subprocess.run`, assert args are a list, no shell, paths with spaces intact); `@render` integration: 2-scene storyboard produces one MP4.
- [ ] **Step 2: Run** `pytest tests/test_scheduler.py -v` -> FAIL.
- [ ] **Step 3: Implement** with `concurrent.futures.ProcessPoolExecutor`; `ManimBackend.render` uses it when `n_scenes > 1`.
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: parallel scene scheduler with ffmpeg concat`

### Task 11: Encoder probe and transcode

**Files:**
- Create: `src/animatica/encode/__init__.py`, `probe.py`, `transcode.py`; Test: `tests/test_probe.py`, `tests/test_transcode.py`

**Interfaces:**
- Produces: `DeviceInfo(vendor: str, name: str)`; `detect_devices(run=subprocess.run, platform: str=sys.platform) -> list[DeviceInfo]` (nvidia-smi / vainfo on Linux, video-controller query on Windows, system_profiler on macOS; any tool missing -> empty, never raises); `EncoderInfo(name: str, codec: str, verified: bool, reason: str)`; `probe_encoders(ffmpeg: str="ffmpeg", run=subprocess.run, cache_dir: Path | None=None) -> list[EncoderInfo]` (ordered per Global Constraints; each candidate must appear in `ffmpeg -encoders` AND pass a 256x256 1s test encode; cached keyed by ffmpeg `-version` output and device list); `pick_encoder(requested: str="auto", infos=None) -> EncoderInfo` (`requested="x264"` forces software; unknown name -> `ValueError` listing choices); `TranscodeResult(path: Path, encoder: EncoderInfo, warning: str | None)`; `transcode(src: Path, dst: Path, enc: EncoderInfo, ffmpeg: str="ffmpeg", run=subprocess.run) -> TranscodeResult` (on non-zero exit or exception: leave `src` untouched, return `path=src`, `warning` set, never raises).

- [ ] **Step 1: Failing tests (all with fake `run`):** fixed `ffmpeg -encoders` text containing `h264_nvenc` and `h264_qsv` with test encodes passing -> order `[nvenc, qsv, x264]`; nvenc listed but its test encode returns 1 -> `verified=False`, reason non-empty, qsv still picked; no ffmpeg (FileNotFoundError) -> only x264 entry with reason mentioning ffmpeg; second `probe_encoders` call reads cache (fake `run` call count unchanged); `pick_encoder("auto")` returns first verified; transcode failure keeps `src` and sets `warning`; transcode args are a list and never contain `shell=True`.
- [ ] **Step 2: Run** `pytest tests/test_probe.py tests/test_transcode.py -v` -> FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: verified hardware encoder probe and safe transcode`

### Task 12: AI core — templates, cache, repair loop

**Files:**
- Create: `src/animatica/ai/__init__.py`, `base.py`, `template.py`, `repair.py`, `src/animatica/storyboard/cache.py`; Test: `tests/test_template.py`, `tests/test_repair.py`, `tests/test_cache.py`

**Interfaces:**
- Consumes: `Storyboard`, `ComponentRegistry`, `safety`.
- Produces: `class AIProvider(Protocol)`: `name: str`, `generate(prompt: str, schema: dict) -> str`; `extract_json(text: str) -> dict` (handles ```json fences, leading/trailing prose, first balanced `{...}`; raises `ValueError` if none); `class TemplateMatcher` with `match(prompt: str) -> Storyboard | None` and `list_templates() -> list[tuple[str, str]]` (name, example prompt); at least 10 templates covering: title card, equation/theorem, function graph, bar chart, steps, shape morph, flow diagram, code walkthrough, definition + example, comparison; `generate_storyboard(prompt: str, provider: AIProvider, registry: ComponentRegistry, max_retries: int=2) -> Storyboard` (one initial call; on parse or validation failure re-calls with the first 6 errors appended; after `max_retries` raises `StoryboardGenerationError` with the last errors); `StoryboardCache(dir: Path)` with `key(prompt, provider, schema_version) -> str`, `get(key) -> Storyboard | None`, `put(key, sb) -> None`.

- [ ] **Step 1: Failing tests:** `extract_json('```json\n{"a":1}\n```') == {"a":1}`; prose-wrapped JSON parses; text with no JSON raises; fake provider returning bad JSON then good JSON -> 2 calls, valid result; fake provider always bad -> exactly 3 calls total then `StoryboardGenerationError`; feedback prompt contains at most 6 error lines; every template's example prompt matches itself and yields a registry-valid storyboard; nonsense prompt -> `None`; cache: same inputs same key, different provider different key, put/get roundtrip.
- [ ] **Step 2: Run** `pytest tests/test_template.py tests/test_repair.py tests/test_cache.py -v` -> FAIL.
- [ ] **Step 3: Implement.** Template matching is keyword/regex based; templates fill `Storyboard` objects directly (no LLM).
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: template matcher, JSON extraction, repair loop, cache`

### Task 13: Real providers and router

**Files:**
- Create: `src/animatica/ai/groq.py`, `openrouter.py`, `nim.py`, `ollama.py`, `router.py`, `providers.toml`; Test: `tests/test_providers.py`, `tests/test_router.py`

**Interfaces:**
- Consumes: `AIProvider`, `Config`, `load_key`.
- Produces: four provider classes implementing `generate`, each using `httpx` with a 60s timeout and structured output where supported (JSON-schema mode for Groq/OpenRouter/NIM where available, JSON mode otherwise, `format` for Ollama); `get_provider(name: str, config: Config) -> AIProvider` (`auto` returns first configured; cloud providers refuse with an actionable message unless `config.cloud_allowed`); `RateLimited(retry_after: float | None)` raised on HTTP 429; `providers.toml` holds `[groq] model=...`, `[openrouter] model=...:free`, `[nim] model=...`, `[ollama] model=...` (values chosen at implementation time after checking each provider's current free models; record the check date in a comment).

- [ ] **Step 1: Failing tests (use `httpx.MockTransport`, no network):** each provider sends the Authorization header from `load_key` and never logs the key; 429 -> `RateLimited` with parsed `retry_after`; 500 -> clear error naming the provider; `get_provider("groq", Config(cloud_allowed=False))` raises with the exact `setup` command to run; `auto` with no keys returns the template-only path (`None`) rather than raising; openrouter refuses a model not ending in `:free` unless `providers.toml` sets `allow_paid=true`.
- [ ] **Step 2: Run** `pytest tests/test_providers.py tests/test_router.py -v` -> FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: groq, openrouter, nim, ollama providers and router`

### Task 14: doctor, setup, guide

**Files:**
- Create: `src/animatica/doctor.py`, `src/animatica/setup_wizard.py`, `docs/GUIDE.md`, `tests/test_doctor.py`, `tests/test_guide.py`; Modify: `cli.py`, `pyproject.toml` (package data for `GUIDE.md`)

**Interfaces:**
- Consumes: `probe_encoders`, `load_config`, `load_key`.
- Produces: `CheckResult(name: str, ok: bool, detail: str, fix: str)`; `run_checks(run=subprocess.run, which=shutil.which) -> list[CheckResult]` covering Python version, Manim importable, LaTeX (`latex` and `dvisvgm`), ffmpeg, Cairo/Pango import via Manim, encoders, configured provider, key present; every failed check has a non-empty exact `fix` string for the user's OS; `doctor --fix` offers (prompt, default No) to install TinyTeX via its official installer script/package for the detected OS, never without confirmation; CLI commands `doctor`, `setup` (choose provider, paste key via hidden input, set `cloud_allowed`, then run checks), `guide` (prints `docs/GUIDE.md` shipped as package data). `docs/GUIDE.md` has the 11 sections of spec section 12.

- [ ] **Step 1: Failing tests:** with fake `which` returning `None` for `latex`, `run_checks` marks LaTeX failed with a `fix` mentioning TinyTeX; all-present fakes -> all `ok`; `animatica guide` output contains each of the 11 section headings from the spec; `GUIDE.md` mentions `py -m` for Windows and every CLI command in the spec (`setup`, `doctor`, `make`, `templates`, `guide`); a test greps `GUIDE.md` troubleshooting table for the exact strings emitted by `doctor` fixes so the two cannot drift.
- [ ] **Step 2: Run** `pytest tests/test_doctor.py tests/test_guide.py -v` -> FAIL.
- [ ] **Step 3: Implement** and write `GUIDE.md` for readers who have never used a terminal (each step: exact command, expected output, what to do if it differs).
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: doctor, setup wizard and beginner guide`

### Task 15: `make` command end to end

**Files:**
- Create: `src/animatica/pipeline.py`, `tests/test_pipeline.py`, `tests/test_make_cli.py`; Modify: `cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `make_video(prompt: str | None, storyboard_path: Path | None, out_dir: Path, *, provider: str="auto", quality: str="standard", encoder: str="auto", preview: bool=False, backend: str="manim") -> MakeResult(video: Path, storyboard: Path, captions: Path, report: Path, warnings: list[str])`; CLI `animatica make "prompt" -o DIR [--preview --quality --encoder --provider --from storyboard.json --debug]` and `animatica templates`, `animatica bench`. Flow: cache -> template -> provider -> validate -> save `storyboard.json` -> backend render -> optional transcode (only when `--encoder` resolves to a hardware encoder or `--fast`) -> write `captions.vtt` from beat captions and component durations -> `report.json`. Always prints provider used (and "(local)" or "(cloud)") and encoder used.

- [ ] **Step 1: Failing tests (fake backend and fake provider):** template prompt makes zero provider calls; empty or whitespace prompt exits non-zero with a message and no files; `--from storyboard.json` skips AI; `captions.vtt` cue times are cumulative sums of beat durations; output dir with spaces and unicode (`tmp_path / "my vidéo 日本"`) works and files land there; invalid storyboard from `--from` prints the first validation errors and exits 2; `--debug` absent -> no traceback in output on provider failure; `@render` end-to-end: `make "title card Hello"` at `--preview` yields MP4 + vtt + json + report.
- [ ] **Step 2: Run** `pytest tests/test_pipeline.py tests/test_make_cli.py -v` -> FAIL.
- [ ] **Step 3: Implement** `bench` as: run the reference prompts through `make_video` (preview) and print a per-stage table from the reports.
- [ ] **Step 4: Run** -> PASS.
- [ ] **Step 5: Commit** `feat: make command, captions, bench`

### Task 16: Conformance corpus, reference prompts, CI, docs, Rust placeholder

**Files:**
- Create: `tests/conformance/*.json` (10 storyboards) + `tests/conformance/expected.json`, `tests/test_conformance.py`, `tests/reference_prompts.txt` (30 prompts), `tests/test_reference_prompts.py`, `.github/workflows/ci.yml`, `docs/COMPONENTS.md`, `rust/README.md`

**Interfaces:**
- Consumes: `RenderBackend`, `default_registry`.
- Produces: `conformance_check(backend: RenderBackend, tmp: Path) -> list[str]` (failures) used by any present or future backend; `expected.json` holds per-storyboard scene count and total duration (+-0.2s). `rust/README.md` documents the backend and `animatica_native` contracts from spec section 16.2 and the 40% rule; no code.

- [ ] **Step 1: Failing tests:** `ManimBackend` passes the corpus (`@render`); a fake backend with wrong durations is reported; 10 designated reference prompts resolve via templates with zero provider calls (no network); `COMPONENTS.md` lists every registered component name (test compares against `default_registry().names()`); CI workflow file lists ubuntu, macos, windows.
- [ ] **Step 2: Run** `pytest tests/test_conformance.py tests/test_reference_prompts.py -v` -> FAIL.
- [ ] **Step 3: Implement** corpus, workflow (installs TinyTeX and ffmpeg per OS, runs non-render tests everywhere and render tests on Ubuntu), docs.
- [ ] **Step 4: Run** full suite `pytest -q` -> PASS (render tests skipped if environment lacks Manim/LaTeX; state the skip count).
- [ ] **Step 5: Commit** `test: conformance corpus, reference prompts, CI and docs`

---

## Self-Review (done)

- **Spec coverage:** s4 pipeline -> T9, T12, T15; s5 schema -> T2; s6 components -> T6-8; s7 LaTeX -> T3, T6, T14; s8 providers -> T12-13; s9 encode -> T11, T15; s10 CLI -> T1, T14, T15; s11 errors -> T6, T9, T11, T15; s12 guide -> T14; s13 layout -> T1-T16; s14 testing -> T16 plus per-task tests; s16 seams -> T7, T8, T9, T10, T16 and reporting in T9.
- **Type consistency:** `Component.play` and `duration` signatures are identical in T4, T6-8, T9; `RenderResult`/`RenderOptions` defined in T9 and consumed in T10, T15, T16; `EncoderInfo` defined in T11 and consumed in T14, T15.
- **Proportion:** plan is bodies-free apart from algorithm hints; signatures and test assertions only.


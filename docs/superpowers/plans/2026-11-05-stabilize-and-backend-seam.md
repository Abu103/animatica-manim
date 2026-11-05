# Stabilize and Backend Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the verified renderer bugs (F1-F4), wire the existing backend seam into `make` (F5-F7), with every change test-first.

**Architecture:** Pure helpers carry the logic so tests need no Manim; `play()` only applies helper output. `make_video` resolves a backend by name from `default_backends()`. Scene parallelism uses threads because each unit already is a subprocess.

**Tech Stack:** Python 3.10+, pydantic v2, typer, pytest, Manim 0.22.1 (pinned).

**Spec:** `docs/superpowers/specs/2026-11-05-renderer-neutral-explainer-design.md`

## Global Constraints

- Storyboard v1 JSON stays valid: max 12 scenes, 8 beats per scene, 300 chars per text field. No schema break.
- Manim stays pinned at `manim==0.22.1`; Manim imports stay inside `play()` bodies and `backends/manim_backend.py`.
- A failing beat degrades to a text card plus a warning; it never aborts the video.
- `docs/COMPONENTS.md` must match `default_registry().names()` (existing drift test).
- Every task ends with bare `pytest -q` green (baseline: 345 passed) and a commit.
- Baseline command: `.venv/bin/python -m pytest -q -p no:cacheprovider`.

## Review Focus

Failure modes the spec implies that no existing test covers, most likely first:

1. `swap: [1, 1]` (same index twice) must be a no-op, not a crash or a vanishing box. Pinned in Task 1.
2. Duplicate values (`[3, 3, 1]`) must swap by index, not by value. Pinned in Task 1.
3. Graph label when LaTeX is missing must fall back to readable text plus a warning. Pinned in Task 3.
4. `--backend nope` must exit non-zero with a message listing valid names, no traceback. Pinned in Task 5.
5. Same prompt with a different `--model` must not hit the cache. Pinned in Task 4.

---

### Task 1: array_viz swap and step timing (F1)

**Files:**
- Modify: `src/animatica/components/array_viz.py`
- Test: `tests/test_array_viz.py`

**Interfaces:**
- Produces: `Point = tuple[float, float, float]`
- Produces: `swap_targets(centers: list[Point], i: int, j: int) -> list[tuple[int, Point]]` returns `[(i, centers[j]), (j, centers[i])]` from the ORIGINAL centers, or `[]` when `i == j`.

- [ ] **Step 1: Write the failing tests**

```python
from animatica.components.array_viz import swap_targets

def test_swap_targets_reads_original_centers():
    c = [(-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
    assert swap_targets(c, 0, 2) == [(0, (1.0, 0.0, 0.0)), (2, (-1.0, 0.0, 0.0))]

def test_swap_same_index_is_noop():
    assert swap_targets([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], 1, 1) == []

def test_swap_with_duplicate_values_uses_indices():
    c = [(-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
    assert [ix for ix, _ in swap_targets(c, 0, 1)] == [0, 1]
```

Add one `@pytest.mark.render` test reproducing F1 (values `[5, 9, 1]`, `swap [0, 2]`, `config.dry_run = True`, using the spy approach from the review): assert the x-centers of the "5" and "1" boxes differ after the step.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_array_viz.py -v`
Expected: FAIL with `ImportError: cannot import name 'swap_targets'`; the render test fails with both x equal to 1.14.

- [ ] **Step 3: Implement `swap_targets` and use it in `play()`**

In `play()` replace the two sequential `clock.play` moves with one `clock.play(*[boxes[k].animate.move_to(pt) for k, pt in swap_targets(centers, i, j)], run_time=0.8)`, then swap list entries. Compute `centers` with `[tuple(b.get_center()) for b in boxes]` before animating. Give each step a 0.8 s budget: highlight-only steps play for 0.8 s total (divide across indices), so actual time equals the declared `2.0 + 0.8 * len(steps)`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_array_viz.py -v`
Expected: PASS, and no `timing:` warning when rendering `tests/conformance/array_viz.json`.

- [ ] **Step 5: Full suite and commit**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
git add src/animatica/components/array_viz.py tests/test_array_viz.py
git commit -m "fix(array_viz): swap both boxes simultaneously from original centers"
```

### Task 2: array_viz draws low/high/mid (F2)

**Files:**
- Modify: `src/animatica/components/array_viz.py`
- Test: `tests/test_array_viz.py`

**Interfaces:**
- Produces: `opacity_for(ix: int, low: int | None, high: int | None) -> float`: `1.0` when `low`/`high` are `None` or `low <= ix <= high`, else `0.25`.
- Consumes: `Params` from Task 1's file (unchanged).

- [ ] **Step 1: Write the failing tests**

```python
from animatica.components.array_viz import opacity_for

def test_opacity_inside_range_is_full():
    assert opacity_for(3, 2, 5) == 1.0

def test_opacity_outside_range_is_dimmed():
    assert opacity_for(0, 2, 5) == 0.25
    assert opacity_for(6, 2, 5) == 0.25

def test_opacity_without_range_is_full():
    assert opacity_for(0, None, None) == 1.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_array_viz.py -k opacity -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `opacity_for` and apply it**

In the step loop, when a step has `low`/`high`, animate each box's opacity to `opacity_for(...)`; when it has `mid`, color that box `colors.accent`. These count inside the same 0.8 s step budget.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_array_viz.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

```bash
git add src/animatica/components/array_viz.py tests/test_array_viz.py
git commit -m "feat(array_viz): visualize binary-search low/high/mid"
```

### Task 3: graph label as math with fallback (F3)

**Files:**
- Modify: `src/animatica/components/graph.py`
- Test: `tests/test_components_charts.py`

**Interfaces:**
- Consumes: `latex_to_plain(latex: str) -> str` from `components/_latex.py`; `warn(scene, message)`, `explain_latex_failure(exc)`.
- Produces: `looks_like_math(label: str) -> bool` in `graph.py`; `make_label(scene, text: str, colors) -> Mobject`.

- [ ] **Step 1: Write the failing tests**

```python
from animatica.components.graph import looks_like_math

def test_looks_like_math():
    assert looks_like_math("x^3/6")
    assert looks_like_math("y = x^2")
    assert looks_like_math(r"\sin(x)")
    assert not looks_like_math("Sine wave")
    assert not looks_like_math("Growth of terms")
```

Add a test that monkeypatches `manim.MathTex` to raise, calls `make_label` with a fake scene exposing `warnings: list`, and asserts a `Text` is returned, `scene.warnings` has one entry, and the Text content equals `latex_to_plain("x^3/6")`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_components_charts.py -k "math or label" -v`
Expected: FAIL with `ImportError: cannot import name 'looks_like_math'`.

- [ ] **Step 3: Implement**

`looks_like_math` is true when the label contains `^`, `_`, `\`, or `/` between alphanumerics. `make_label` returns `MathTex` for math labels and `Text` otherwise; on any exception from `MathTex` it warns and returns `Text(latex_to_plain(text))`. Use it in `Graph.play` in place of the direct `Text(p.label, ...)`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_components_charts.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

```bash
git add src/animatica/components/graph.py tests/test_components_charts.py
git commit -m "fix(graph): typeset math labels with plain-text fallback"
```

### Task 4: cache key covers model, mode and registry (F4)

**Files:**
- Modify: `src/animatica/pipeline.py:75-77`, `src/animatica/components/registry.py`
- Test: `tests/test_pipeline.py`, `tests/test_registry.py`

**Interfaces:**
- Produces: `Registry.fingerprint() -> str` (sha256 hex of sorted `name:api_version` pairs).
- Produces: `cache_variant(prov, two_stage: bool, registry) -> str` in `pipeline.py`, returning `f"{prov.name}:{prov.model}|{'two' if two_stage else 'one'}|{registry.fingerprint()}"`. `make_video` passes it as the `provider` argument of `cache.key`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cache_variant_differs_by_model(registry):
    a = SimpleNamespace(name="nim", model="m1"); b = SimpleNamespace(name="nim", model="m2")
    assert cache_variant(a, False, registry) != cache_variant(b, False, registry)

def test_cache_variant_differs_by_mode(registry):
    p = SimpleNamespace(name="nim", model="m1")
    assert cache_variant(p, True, registry) != cache_variant(p, False, registry)

def test_registry_fingerprint_stable_and_changes(registry):
    assert registry.fingerprint() == registry.fingerprint()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py tests/test_registry.py -v`
Expected: FAIL with `ImportError` / `AttributeError: fingerprint`.

- [ ] **Step 3: Implement and use in `make_video`**

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py tests/test_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

```bash
git add src/animatica/pipeline.py src/animatica/components/registry.py tests/test_pipeline.py tests/test_registry.py
git commit -m "fix(cache): key includes model, two-stage mode and registry fingerprint"
```

### Task 5: `--backend`, single report writer (F6, F7)

**Files:**
- Modify: `src/animatica/pipeline.py:107-115`, `src/animatica/cli.py` (`make`), `src/animatica/report.py`, `src/animatica/backends/manim_backend.py`
- Test: `tests/test_pipeline.py`, `tests/test_make_cli.py`, `tests/test_backend_manim.py`

**Interfaces:**
- Consumes: `default_backends() -> dict[str, RenderBackend]` from `animatica.backends`.
- Produces: `resolve_backend(name: str) -> RenderBackend` in `pipeline.py`; raises `ValueError(f"unknown backend {name!r}; available: a, b")`.
- Produces: `write_report(path, stage_times, warnings, backend: dict[str, str] | None = None)` adds a `"backend"` key only when given.
- Produces: CLI option `--backend TEXT` (default `"manim"`).

- [ ] **Step 1: Write the failing tests**

```python
def test_resolve_backend_unknown_lists_available():
    with pytest.raises(ValueError, match=r"unknown backend 'nope'; available: .*manim"):
        resolve_backend("nope")

def test_report_records_backend(tmp_path):
    write_report(tmp_path / "r.json", {"a": 1.0}, [], backend={"name": "manim", "version": "0.22.1"})
    assert json.loads((tmp_path / "r.json").read_text())["backend"]["name"] == "manim"

def test_cli_unknown_backend_exits_nonzero_without_traceback():
    r = CliRunner().invoke(app, ["make", "graph of sin(x)", "--backend", "nope"])
    assert r.exit_code != 0 and "Traceback" not in r.output and "available:" in r.output
```

Add a test with an injected fake backend (registered through `monkeypatch` on `default_backends`) proving `make_video(backend="fake")` calls it and not `ManimBackend`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py tests/test_make_cli.py -k "backend or report" -v`
Expected: FAIL (`resolve_backend` missing, no `--backend` option).

- [ ] **Step 3: Implement**

`make_video` calls `resolve_backend(backend)` instead of the hard-coded check. Remove the `write_report` call from `ManimBackend.render`; `make_video` is the single writer and passes `backend={"name": b.name, "version": getattr(b, "version", "unknown")}`. Add `version = manim.__version__` lookup to `ManimBackend` as a property.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py tests/test_make_cli.py tests/test_backend_manim.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite, smoke, commit**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider && .venv/bin/python scripts/ci_smoke.py
git add -A src tests
git commit -m "feat(cli): --backend selects renderer; report.json records backend"
```

### Task 6: opt-in `--jobs` scene parallelism (F5)

**Files:**
- Modify: `src/animatica/backends/scheduler.py`, `src/animatica/backends/manim_backend.py`, `src/animatica/cli.py`, `src/animatica/pipeline.py`
- Test: `tests/test_scheduler.py`, `tests/test_backend_manim.py`

**Interfaces:**
- Consumes: `RenderOptions.jobs: int | None`.
- Produces: `render_scenes_parallel(render_one: Callable[[int], Path], n_scenes: int, jobs: int | None = None) -> list[Path]` (same signature, now backed by `ThreadPoolExecutor`; a closure no longer needs to be picklable).
- Produces: CLI `--jobs INT` (default `1`; values below 1 are rejected by typer `min=1`).

Root cause note: the current `ProcessPoolExecutor` requires a picklable callable. `ManimBackend` would pass a closure, which fails on Windows (spawn) and caused the `fork()` deprecation warnings in the suite. Each scene is already a `manim` subprocess, so threads give the same parallelism.

- [ ] **Step 1: Write the failing tests**

```python
def test_parallel_accepts_unpicklable_closure(tmp_path):
    marker = object()
    def render_one(i): return tmp_path / f"{i}.mp4"   # closure over local state
    assert render_scenes_parallel(render_one, 3, jobs=2) == [tmp_path / f"{i}.mp4" for i in range(3)]

def test_cli_jobs_zero_rejected():
    r = CliRunner().invoke(app, ["make", "graph of sin(x)", "--jobs", "0"])
    assert r.exit_code != 0
```

Add a backend test with a monkeypatched `subprocess.run` verifying scene outputs are concatenated in scene order when `jobs=2`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_scheduler.py -v`
Expected: FAIL with a pickling error on the closure.

- [ ] **Step 3: Implement**

Switch the pool to `ThreadPoolExecutor`; keep first-failure cancellation and the `scene {idx} failed:` message. Refactor `ManimBackend.render` so the per-scene body is `_render_scene(i) -> Path`, called through `render_scenes_parallel(..., jobs=opts.jobs or 1)`. Per-scene warnings files already have unique names (`warnings_{i}.json`).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_scheduler.py tests/test_backend_manim.py -v`
Expected: PASS, and the four `fork()` DeprecationWarnings from the baseline are gone.

- [ ] **Step 5: Measure, full suite, commit**

```bash
time .venv/bin/python -m animatica make --from docs/gallery/fibonacci.json -o /tmp/j1 --preview --jobs 1
time .venv/bin/python -m animatica make --from docs/gallery/fibonacci.json -o /tmp/j4 --preview --jobs 4
.venv/bin/python -m pytest -q -p no:cacheprovider
git add -A src tests
git commit -m "feat(render): opt-in --jobs scene parallelism via threads"
```

Keep the default at `1` until the two timings above show a real gain (spec 16.3: measure before changing defaults); record both numbers in `CHANGELOG.md`.

---

## Self-review

- **Spec coverage:** F1-Task 1, F2-Task 2, F3-Task 3, F4-Task 4, F5-Task 6, F6 and F7-Task 5. Open decision (limits) is owner-only and has no task.
- **Step scan:** every code step names file, signature and the spec's exact values; bodies appear only in tests.
- **Type consistency:** `swap_targets` and `Point` (Task 1) are not used by Task 2; `resolve_backend` (Task 5) is consumed by `make_video` only; `RenderOptions.jobs` (existing) is consumed in Task 6.
- **Proportion:** plan is mostly tests and signatures, not implementation bodies.

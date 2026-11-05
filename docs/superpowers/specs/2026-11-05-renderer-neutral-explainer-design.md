# Renderer-neutral Explainer IR: review and design

Date: 2026-11-05 · Base: `main` @ `4f4e56e` · Status: draft for owner approval

## 1. Verified baseline (fresh clone, Linux, via the README one-liner)

- `scripts/bootstrap.sh` finished and `animatica doctor` passed all checks.
- `pytest`: **345 passed**, 0 failed (matches the review doc).
- Not run: Windows, live NIM, HyperFrames.

## 2. Root-cause findings (systematic-debugging, evidence first)

| # | Finding | Evidence | Root cause |
|---|---------|----------|-----------|
| F1 | `array_viz` swap overlaps two items | Real Manim run, values `[5,9,1]`, `swap [0,2]`: after the step "1" and "5" are both at x=1.14 | `play()` runs two *sequential* moves; the second target is read from `boxes[i].get_center()` after `boxes[i]` already moved to `j`'s slot |
| F2 | `array_viz` `low/high/mid` validate but never draw | `play()` only reads `highlight` and `swap` | Validator and renderer were written separately; no test ties a schema field to a visible effect |
| F3 | Graph `label` is plain `Text` | `graph.py`: `Text(p.label, ...)`; axis numbers use LaTeX, label does not | Label never routed through the LaTeX/fallback helpers in `_latex.py` |
| F4 | Storyboard cache ignores model and `--two-stage` | `pipeline.py`: `cache.key(prompt, prov.name, "1")`; `prov.name` is `"nim"` for every model | Key omits `prov.model`, mode, and registry/schema fingerprint. `animatica eval --models a,b` and `--model` changes can silently return another model's cached storyboard |
| F5 | `RenderOptions.jobs` and `render_scenes_parallel` are dead code | `grep jobs`: only defined in `base.py`/`scheduler.py`; `ManimBackend.render` uses a plain `for` loop | Spec section 16.2(3) was implemented as a library but never wired |
| F6 | Backend seam is not reachable | `make_video` hard-codes `ManimBackend()`; CLI has no `--backend`; `default_backends()` has no caller | Seam exists, pipeline does not use it |
| F7 | `report.json` written twice | Written by `ManimBackend.render` and again by `make_video` | Duplicate responsibility (harmless today, wrong once a second backend exists) |

Owner decision still open from `AUDIT_TASKS.md` finding 13: whether to raise `MAX_SCENES/MAX_BEATS/MAX_TEXT`. Recommendation: keep 12/8/300. The limits are what keep weak models inside renderable sizes, and nothing here needs more.

## 3. Design

Animatica becomes a **structured explainer compiler**: the model fills validated data, never code.

```
prompt -> planner -> Storyboard v1 (unchanged, stays the LLM contract)
       -> lint/validate -> backend capability check -> adapter -> encode/captions/report
```

### 3.1 Keep storyboard v1 as the IR (YAGNI)
The review doc proposes a new semantic IR with `visual intents`. Today's components (`equation`, `graph`, `array_viz`, `compare`, `timeline`...) already *are* semantic intents: they carry data and no renderer calls. Introducing a second schema now would duplicate them and break the `--from` JSON files in `docs/gallery/`. Decision: **no IR v2 until a second backend proves v1 insufficient.** Version field and migrations already exist.

### 3.2 Split the component contract
Today `Component.play(scene, p, colors)` takes a Manim `Scene`. Change in two steps, both backward compatible:
1. Add `Component.requires: ClassVar[frozenset[str]]` (capability tags such as `{"math"}`, `{"graph"}`). Default `frozenset()`.
2. Backends expose `capabilities() -> frozenset[str]` and a component list. `make_video` rejects a storyboard whose components a chosen backend cannot draw, *before* rendering.
`play()` stays Manim-specific and moves behind the Manim adapter only when the second adapter exists.

### 3.3 Backend selection
`make_video(backend=...)` resolves through `default_backends()`. CLI gets `--backend`. `report.json` records `{"backend": {"name", "version"}}`. Manim stays default.

### 3.4 Second backend: HyperFrames, with p5 inside it
Verified from <https://github.com/heygen-com/hyperframes> (page loaded 2026-11-05): Apache-2.0; HTML/CSS compositions with `data-start`/`data-duration`; seeks each frame in headless Chrome and encodes with FFmpeg; Node.js 22+ and FFmpeg required; animation through GSAP/CSS/Lottie/Three.js/WAAPI or a custom frame adapter.
- Build **one** HTML-based backend, not a separate p5 encoder. p5 sketches run *inside* HyperFrames for canvas visuals, driven by an explicit timestamp (`noLoop()` plus `redraw()` per seek, seeded `randomSeed`, fixed size). No wall-clock.
- Keep Manim for LaTeX and axes. No hybrid per-scene routing until both backends pass the same conformance corpus.
- Security: HTML is generated from trusted templates with escaped values only. No model-provided HTML, JS, or CSS ever. Pin script URLs to exact versions.
- **Unverified, spike first:** HyperFrames CLI flags, Chrome download in locked-down environments, and whether an HTML math path (KaTeX) matches Manim's look.

### 3.5 Frame QA (roadmap P1.3, now concrete)
`animatica qa out/video.mp4`: sample N frames with the bundled ffmpeg, flag empty frames, content outside the safe area, and low contrast. Deterministic pixel checks only; no VLM until the NIM id is shown to accept images.

## 4. Order of work

| Plan | Scope | Gate |
|------|-------|------|
| **A (written)** `2026-11-05-stabilize-and-backend-seam.md` | F1-F6 fixes, `--backend`, `--jobs` | `pytest -q` green + `ci_smoke.py` |
| B (not written) | Capability negotiation, frame QA | Plan A merged |
| C (not written) | HyperFrames spike, then adapter | Spike renders one beat deterministically twice with identical frame hashes |

B and C stay unwritten on purpose: C depends on spike results that need Node 22, Chrome, and network, none of which this sandbox could verify.

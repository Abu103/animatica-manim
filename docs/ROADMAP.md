# Animatica roadmap / design spec (DRAFT, needs owner approval)

## Goal (as understood, correct me)
Prompt in, correct and decent-looking explainer video out, **driven by free/weak models** (Nemotron 3 Super 120B-A12B, Ultra 550B-A55B via NIM/OpenRouter, Hermes Agent). Stable enough to demo and put on a portfolio. Not a general Manim-code writer.

## Core principle
Weak models are bad at: long outputs, layout maths, spotting their own mistakes, writing Manim code (hallucinated APIs, overlapping text; see ManiBench, OmniManim).
Weak models are fine at: picking from a small menu, filling short JSON, following examples.
So: **model chooses + fills, code does everything else.** Animatica already works this way (fixed components + schema validation + repair). Keep it. Push quality into deterministic code, never into prompts alone.

## What research says (web, Nov 2026)
- Planner then coder split works (Manimator). We do planner then *fill*, no code writing.
- Ground the model in docs/examples before it writes (PhysicsSolutionAgent used a docs vector DB). Our equivalent: component catalog + 1 worked example per component in the prompt.
- Executable is not the same as good: render-time failures (overlap, overflow, clipped text) dominate (OmniManim). Our equivalent: frame lint after render.
- Nemotron 3 Super lists tool use as an intended use; NVIDIA model card advice is temperature 1.0, top_p 0.95 (from third-party guides citing the card; check the card yourself).
- Not verified: whether your `nemotron-3.5-super-vl` id accepts images (name says VL). Test with one image before building the VLM critique loop.

## Architecture additions (in priority order)

### P0 Stabilise (small, existing flows) -- the "show others" bar
A. `bounce_sequence`: cap 12 -> 20 terms; prompt: never split one sequence across scenes.
B. `scale: linear|sqrt|log` on bounce_sequence and bar_chart; labels keep true values; min bar height so 0..5 still shows.
C. Lint/repair pass (no LLM): drop duplicate/redundant scenes, enforce order title -> definition -> demo -> summary, merge consecutive scenes of the same sequence, clamp text lengths, fix captions that mention objects not drawn.
D. Demo gallery + README gif, GitHub Actions smoke test, pin manim.
Acceptance: re-run the Fibonacci 0..15 prompt on nemotron, one scene, 16 terms, no warnings.

### P1 Make weak models reliable
1. **Two-stage generation**: stage 1 outline (scene list: component + one-line intent, tiny JSON); stage 2 fill params per scene, one call each, each validated and retried alone. Short outputs = fewer failures, cheap retries, partial caching.
2. **Eval harness** `animatica eval --provider X`: reference prompts, deterministic scores (valid on 1st try, retries, lint warnings, duration). Multi-provider `--models` deferred to Phase 2.1.
3. **Frame lint** after render: extract keyframes, check pixels (empty frame, content outside safe area, text too small, low contrast). Deterministic first. Optional VLM critique with the same model if vision works.
4. **Error messages written for LLMs**: every validation error says field, bad value, allowed values, and a fixed example. Retries get much better.

### P2 Hermes / agent integration (this is how weak models "build" things)
- `animatica mcp` (or plain JSON-CLI): tools `list_components`, `component_schema`, `validate_storyboard`, `render_storyboard`, `preview_frame(scene, t)`, `lint_video`. Hermes writes storyboard JSON, validates, fixes, renders, looks at frame. No Manim code touched.
- Ship `skills/animatica/SKILL.md` telling an agent the loop: outline, validate, render, lint, fix.
- `animatica edit out/ "slow down scene 3"`: model edits a few JSON fields (tiny diff, hard to break).
- Not verified: Hermes Agent's exact MCP/skill format. Check its docs before building.

### P3 More components (each is a small independent task for a weak model)
`number_line`, `array_viz` (sort/search steps), `recursion_tree` (Fibonacci call tree, huge for this demo), `table`, `timeline`, `compare` (2 columns), `matrix`, `code_walkthrough` (step through lines + variable panel), `formula_derivation`, `stat_callout`, `flow` (better than diagram), `parametric_graph`.
Scaffold: `animatica new-component <name>` generates module, Params model, test, conformance JSON, doc row. The model only fills `play()`. Conformance + render smoke test gate it.

### P4 Useful products on top
- Narration (TTS, timed to captions), vertical 9:16 export, themes.
- `--research`: pull facts from the web into the outline so videos are about real content (Bright Data `bdata discover` or free search; needs login/keys, optional).
- Doc/README to video, code repo to explainer, PDF page to video.
- Web UI (Streamlit) once P0-P2 are stable.

## Splitting work: weak models vs Claude
- Weak models (Hermes + Nemotron): P3 components, new reference prompts, docs, gallery. Each task card in `docs/TASKS_FOR_HERMES.md` has files, steps and an acceptance command.
- Claude sessions: P0, P1, P2 (design-heavy), reviewing/fixing whatever the weak models leave broken. Rule: nothing merges unless `pytest -q` and `animatica doctor` pass.

## Risks
- Letting a model write component code means running its code. Keep that dev-time only, in the repo, reviewed. Never run model-written code at `make` time.
- Free model rate limits: caching per scene + resume matters.
- Windows: untested by me. Do a clean-clone test on your machine before showing.

## Decision needed
Approve this, or tell me what to cut/reorder. Nothing past P0 gets coded until you say yes.


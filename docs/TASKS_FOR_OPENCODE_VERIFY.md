# Task cards: compute-and-verify (V1 to V3), written for opencode

Design (read it first, it is the contract): `docs/superpowers/specs/2026-11-16-compute-and-verify-design.md`.
Rules: `AGENTS.md` applies to every card. One card per session. Fresh session per card.
Integration branch: `dev`. Branch per card: `hermes/<card-id>-<slug>` off `dev`. Deliver a patch; do not push (rule 6).
Reviewer: Claude reads every card's patch before the next card starts (Gate B).

## How to work (read once)

- Setup: `. ./.animatica-env` after `sh scripts/sandbox.sh` (see AGENTS.md). Fast loop: `python -m pytest -q tests/<file>`; before handing in: `python -m pytest -q -n auto tests` and `ruff check src tests`.
- Tests first. Write the test, run it, read the failure, then write the code. Paste the red output and the green output in the report.
- Everything in `src/animatica/verify/` imports **no Manim**. A test imports it with Manim absent from `sys.modules` (see card V1a for the exact test).
- Never hand-wave a number. Where a card gives an expected value, it was computed with numpy. Where a card says "compute and record", run the code, read the number, and put that number in the test.
- Stop conditions (write a handoff packet, do not improvise): a card needs a 6th file; two fix attempts failed; a test in the card cannot pass without weakening it; a design sentence contradicts the code you find.
- Report format at the end of each card: files changed, commands run with real output, `Verified:` list, `Unverified:` list, `Deviations from the card:` list (empty is fine, say "none").

## Shared definitions (every card uses these)

```python
# src/animatica/verify/facts.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Fact:
    kind: str        # "range" | "extremum" | "zero" | "total" | "ratio" | "sorted" | "value" | "peak" | "domain" | "clipped"
    subject: str     # what it is about: "fn", "approx_fn", "bars", "final_state", "signal"
    value: object    # float | int | bool | str | tuple[float, ...]
    text: str        # one plain sentence, written for a model: "fn has 2 local maxima at x = 1.57, 7.85"
```

`Component` (in `components/base.py`) gets two non-abstract members, nothing else changes there:

```python
domain: ClassVar[str] = ""          # "" = not checked by the domain rule; "plain axes" | "frequency"
def facts(self, p: BaseModel) -> "list[Fact]":
    return []                       # pure function of params; no Manim
```
Import `Fact` under `TYPE_CHECKING` so base.py stays light.

Severity words used below: **error** = a finding that V2 will send back to the model; **warn** = shown in the report only. In V1 both are only printed as warnings (no loop yet).

A `Finding` is `{severity, beat: (scene_idx, beat_idx), field: "caption"|"narration"|"params", message}`, a frozen dataclass in `verify/__init__.py`.

---

## V1a  Facts core + `graph` facts  [Gate A: skip, design approved]

Why: first piece of the facts machinery, plus the component the Fourier failure came through.
Files (5 max): `src/animatica/verify/__init__.py` (Finding), `src/animatica/verify/facts.py` (Fact + `facts_for(registry, beat)`), `src/animatica/components/base.py`, `src/animatica/components/graph.py`, `tests/test_verify_facts_graph.py`.

Steps:
1. In `graph.py` add a pure `_data(p) -> GraphData` (a small dataclass: `segs`, `approx_segs`) that does exactly the `sample_function` + `clip_segments` work that `play()` does now (lines around 320-330). Change `play()` to call `_data(p)`. **`play()` behaviour must not change**: `tests/test_graph.py` stays green untouched.
2. `Graph.domain = "plain axes"`.
3. `Graph.facts(p)` built **only from `_data(p)`** (design 5.1), as `Fact`s:
   - `range` of `fn`: (min y, max y) over the visible points, rounded to 3 decimals.
   - `extremum`: local maxima and minima of `fn` as (kind, x) with x rounded to 2 decimals. A local max is a sample strictly greater than both neighbours **inside one segment** (never across a gap). Cap at 8 of each. Value for the max list: tuple of x's.
   - `zero`: x positions where consecutive samples change sign, linearly interpolated, rounded to 2 decimals, cap 12.
   - `clipped`: True if any finite sample of `fn` lies outside `y_range` (compute from the unclipped samples: call `sample_function` without `y_range` for this one check, or compare the point count before and after clipping; pick one, say which in the report).
   - `domain` fact: value `"plain axes"`, text `"graph draws y against x (time or position); it never draws a frequency spectrum"`.
4. `facts_for(registry, beat) -> list[Fact]`: validates `beat.params` with `comp.Params`, returns `comp.facts(params)`; returns `[]` if the component has no facts or validation fails (never raises).

Tests (`tests/test_verify_facts_graph.py`):
- `sin(x)` on x in (0, 2*pi), y in (-2, 2): range (-1.0, 1.0); one max near x=1.57, one min near x=4.71; zeros near 3.14 (the endpoints 0 and 2*pi are not interior sign changes; **compute and record what your code returns and assert it**, with a comment).
- `x**2` on (-2, 2), y in (0, 1): `clipped` is True; the same on y in (0, 5): False.
- `1/x` on (-1, 1): extrema never straddle the gap (no max/min fact at x=0).
- Agreement test (design 5.1): for 3 functions, the `range` fact equals `min`/`max` taken from `_data(p)` directly, and `play()` is not called.
- `fn="sin(x)+0.5*sin(3*x)"` on (0, 2*pi): **compute and record** the number of local maxima and put it in the test. (The design assumes two. If it is not two, keep the real number and say so in the report; V1d depends on it.)
- No-Manim test: `subprocess.run([sys.executable, "-c", "import sys; import animatica.verify.facts; assert 'manim' not in sys.modules"])` returns 0. (If this fails because `animatica.components` imports Manim at import time, stop and report; do not hack around it.)

Accept: `python -m pytest -q tests/test_verify_facts_graph.py tests/test_graph.py` passes. Do not: change graph drawing, change `SAMPLES`.

---

## V1b  Facts for `bar_chart`, `stat_callout`, `array_viz`

Files: `components/bar_chart.py`, `components/stat_callout.py`, `components/array_viz.py`, `tests/test_verify_facts_simple.py` (4 files).

Steps (same rule as V1a: `facts` reads the same data `play()` reads; if `play()` computes inline, extract a small pure helper, do not copy the logic):
- `bar_chart`: `domain="plain axes"`. Facts: `total` (sum), `extremum` max and min as (label, value), `ratio` largest/smallest when smallest > 0 (rounded to 2 decimals), `value` for every bar as (label, value).
- `stat_callout`: no domain. Fact `value`: the number parsed from `p.value` (strip `,`, `%`, `$`, a trailing `x`, `k`/`M`/`B` multipliers: "2.5M" -> 2500000.0). If it does not parse, no fact. Keep the parser in `verify/facts.py` as `parse_number(text) -> float | None` so V1c reuses it.
- `array_viz`: `domain="plain axes"`. Read the file first to see what its `steps` and values are. Facts: `sorted` = whether the **final** array state is ascending (compute by replaying the swaps from the params; if replaying is not possible from the params, do not invent it: emit no `sorted` fact and say so in the report), and `value` for the max and min element.

Tests: one per component with a hand-computed example. `bar_chart` labels `["A","B","C"]` values `[2, 8, 4]`: total 14.0, max ("B", 8.0), min ("A", 2.0), ratio 4.0. `stat_callout` values: "2.5M" -> 2500000.0, "12%" -> 12.0, "1,234" -> 1234.0, "abc" -> None. `array_viz`: the Fourier case from the design, values `1 0 -1 0 1 0 -1 0` with no swaps: no `sorted` claim of True (it is not sorted; assert False).
Accept: the new test file plus `tests/test_components_charts.py tests/test_stat_callout.py tests/test_array_viz.py` pass.

---

## V1c  Number grounding

Files: `src/animatica/verify/numbers.py`, `tests/test_verify_numbers.py`, `tests/fixtures/verify/` (storyboard JSON fixtures). 3 files.

Public API: `check_numbers(sb, registry) -> list[Finding]`.

Rules (design 5.2, verbatim where it matters):
- Numbers in **caption and narration** of each beat. What counts: digit strings (with `,` thousands, a decimal point, `%`, or a trailing `x`) and the words zero..twenty, hundred, thousand, million. Parse with `parse_number`.
- Free allowlist, never flagged: "one" and "two" used as pronoun or ordinal ("one of", "the two", "first", "second"). Implement as a small set of regexes you list in the report; err toward **not flagging** (anti-goal: over-rejecting). Also never flag a number that is part of a word like "3D" or "2nd".
- Grounding sources, per beat: that beat's params (every number found anywhere in the params dict, recursively, including numbers inside strings), that beat's `facts_for` values, the params and facts of **earlier beats in the same scene**, and `sb.title`. **Earlier captions and narration never ground anything.**
- Match rule: equal after rounding to the number of decimals written in the text; a percent in text matches a source value of `v` or `v*100` (so "12%" is grounded by 0.12 or 12); a word number matches its digit value.
- Severity: error when the number is ungrounded. The message must be written for a model: `caption says "40" but no param or computed fact for this beat equals 40`.
- Extra: a `title_card` beat has few numbers; do not special-case it.

Tests (all without Manim): (1) beat with `stat_callout value="12%"` and caption "grew 12%": no finding. (2) caption "grew 40%" over the same params: one finding, error, field caption. (3) number only in the **previous caption** repeated in the next beat: still a finding (the laundering case). (4) "two peaks" is not flagged (free word) but "three peaks" over params containing no 3 is flagged. (5) "1,234" matches 1234. (6) a bar chart whose total fact is 14 grounds "14 in total". (7) fixture `tests/fixtures/verify/fourier_2026_11_16.json`: **rebuild from the export** in the owner's `files/20-storyboard.json` if available, otherwise write a 3-beat storyboard with the same three problems; run `check_numbers` and assert the findings you get, recorded.
Accept: `python -m pytest -q tests/test_verify_numbers.py` passes. Measure: run `check_numbers` over every storyboard in `tests/conformance/*.json` and `docs/gallery` if they are storyboards; the number of findings must be **0** on the shipped corpus (a finding on a shipped example is a false positive: fix the rule, not the corpus). Paste the count.

---

## V1d  Domain rule and claim patterns

Files: `src/animatica/verify/claims.py`, `tests/test_verify_claims.py`, `src/animatica/components/parametric_graph.py`, `components/bounce_sequence.py`, `components/number_line.py` (add `domain = "plain axes"` only). 5 files.

API: `check_claims(sb, registry) -> list[Finding]`.

1. **Domain rule** (design 5.3). Regex over caption and narration: `frequency domain|frequency spectrum|\bspectrum\b|spectral|power spectrum`. If the beat's component has `domain == "plain axes"`, error: `says "<match>" but <component> draws plain axes, no component currently draws a frequency spectrum`. Components with `domain == ""` are not checked (a title card may say "frequency domain"). If any component with `domain == "frequency"` exists in the registry, change the message tail to `use signal_spectrum`.
2. **Pattern claims**, small and precise, each mapped to one fact kind and only run on a beat whose component produced that fact:
   - `(\d+|two|three|four|five)\s+peaks?` against the count of local maxima (graph) / peak facts (signal_spectrum later): mismatch is an error.
   - `largest|biggest|highest|tallest` on `bar_chart`: mismatch is an error only when a **named label** in the same sentence is not the max label; if no label is named, no check.
   - `sorted` on `array_viz` with the `sorted` fact False: warn.
   Anything else: not checked, never guessed. Keep the table in one list at the top of the file so the owner can read it.
3. Also return the list of **unchecked sentences** via `unchecked_sentences(sb, registry) -> list[tuple[beat, sentence]]` = caption/narration sentences with a number or a pattern-word-free claim nobody checked. Define simply: every sentence that no rule above looked at. V1e reports its count only.

Tests: "frequency domain" over `graph` -> error; over `title_card` -> none; "two peaks" over the V1a sin+0.5 sin(3x) graph: **whatever V1a recorded**, assert the consistent outcome; "three peaks" over a 1-max graph -> error; the Fourier fixture from V1c yields the domain error on its graph beat **and on its narration** and **no** error on its `array_viz` "Superposition" beat (that is the known gap in design 5.3; assert it with a comment).
Accept: `python -m pytest -q tests/test_verify_claims.py tests/test_graph.py tests/test_bounce_sequence.py tests/test_number_line.py`.

---

## V1e  Wire into the pipeline, report block, CLI flags

Files: `src/animatica/verify/__init__.py` (add `verify_storyboard`), `src/animatica/pipeline.py`, `src/animatica/report.py`, `src/animatica/cli.py`, `tests/test_verify_pipeline.py`. 5 files.

Steps:
1. `verify_storyboard(sb, registry) -> VerifyResult` runs `check_numbers` and `check_claims`; result has `findings`, `checked` (count of numbers looked at + pattern matches), `unchecked` (list of strings), `by_severity`.
2. `make_video(..., verify: bool = True, strict: bool = False)`. After `errors = registry.validate(sb)` passes (the params are valid by then), run `verify_storyboard`; add each finding to `warnings` as `verify: scene S beat B <field>: <message>`. Runs for template and `--from` storyboards too, **warn only** (no mutation in V1).
3. `write_report(..., verification: dict | None = None)`; when given, `report.json` gets `"verification": {"checked": n, "passed": n, "fixed": 0, "sent_back": 0, "failed": n, "unchecked": [..]}`. `passed = checked - failed`. Existing reports without the key must still load (do not change `preview_frame`).
4. One console line via the existing progress/announce path (copy how the narration line is printed): `Verified 7 claims, 1 failed, 2 unchecked (see report.json)`. **Never** the words "true", "correct" or "verified facts". Zero checks prints `Nothing to verify`.
5. CLI: `--verify/--no-verify` (default on) and `--strict`. With `--strict`, any surviving `error` finding exits non-zero **after** the report is written. Add both to the MCP `make` tool schema only if the schema is generated from the same option list; otherwise leave MCP alone and say so.
6. Idempotence: running verify twice on the same storyboard gives identical findings (test it).

Tests: a constructed storyboard with an invented figure -> warning in `result.warnings` and `report.json["verification"]["failed"] == 1`; `--no-verify` -> no `verification` key; `--strict` -> non-zero exit (use the existing CLI test harness in `tests/test_make_cli.py` as the pattern, with the template provider so no network is needed).
Accept: `python -m pytest -q tests/test_verify_pipeline.py tests/test_pipeline.py tests/test_make_cli.py`, then `python scripts/ci_tests.py`. Run one **real** end-to-end: `animatica make "bar chart of sales by quarter" --provider template --out /tmp/v1e` and paste the console verification line and the `verification` block.

**V1 is done after V1e.** Stop. Write the milestone handoff packet and wait for Claude's review before V2.

---

## V2a  Mechanical fixes

Files: `src/animatica/verify/fix.py`, `src/animatica/pipeline.py`, `src/animatica/report.py` (record `fixes`), `tests/test_verify_fix.py`. 4 files.

`apply_fixes(sb, registry) -> tuple[Storyboard, list[Fix]]`, `Fix = {beat, field, before, after, reason}`. Only fixes that cannot change meaning:
- `graph` clipped by `y_range` (the `clipped` fact is True): widen `y_range` to the `range` fact with 10% padding, rounded to 2 decimals. Never when the model plainly chose the window to zoom (skip if the fact says the visible range is under 50% of the window? **No**: keep it simple, apply only when `clipped` is True and say so).
- `stat_callout`: when `value` text differs from its parsed number only by formatting ("1234" vs "1,234"), leave it; this card does **not** rewrite stat values. (Listed so you do not add it.)
Fixes are deterministic and idempotent (`apply_fixes` on its own output returns no fixes: test it). The post-fix storyboard is what is written to `storyboard.json`; `report.json["verification"]["fixed"]` and a `fixes` list carry before/after. Captions are never rewritten.
Accept: tests pass; a `--from` re-run of the written `storyboard.json` gives the same result and zero fixes.

## V2b  Facts-based repair loop

Files: `src/animatica/ai/repair.py`, `src/animatica/ai/prompt.py` (only if needed), `src/animatica/pipeline.py`, `tests/test_verify_repair.py`. 4 files.

Design 5.4: generate -> lint -> verify -> fixes -> still `error` findings -> send back (max 2 verify retries, **a separate budget** from the existing schema-retry budget) -> still failing -> degrade (blank that beat's narration; captions untouched) -> record.
- The repair message goes through the **existing errors channel** of `build_prompt(prompt, registry, errors, narrate=...)`: each error string is `scene S beat B caption: "<sentence>" ; the code computed: <fact texts>`. No new prompt template.
- Only on model-generated storyboards. Hand-written `--from` files are verified (V1e) but never sent back and never degraded.
- Provider-call count test: with a fake provider that fails verify once then passes, exactly 2 calls; failing always: 1 + 2 calls, then degrade, run completes with a `verify:` warning.
- The `StoryboardCache` stores the **final** (post-loop) storyboard.
Accept: tests pass; `python -m pytest -q tests/test_repair.py tests/test_two_stage.py` still pass (the loop must not change them). **Unverified until the owner runs a real provider**; say so.

**V2 done: stop for review.**

---

## V3a  `signal_spectrum`: pure data, params, facts (no drawing)

Files: `src/animatica/components/signal_spectrum.py` (class with `Params`, `_data`, `facts`, `duration`, `fallback_text`, and a `play` that raises `NotImplementedError` for now), `tests/test_signal_spectrum.py`. 2 files.

Params: `title: str`; `waves: list[Wave]` with 1 to 4 items; `Wave = {freq: int 1..40, amp: float 0.1..5.0, phase: float -3.2..3.2 (default 0.0)}`; **frequencies must be distinct** (validation error otherwise); `show: Literal["time","spectrum","both"] = "both"`.
`_data(p)`: `N = 256`, `t = np.arange(N)/N`, `x = sum(a*sin(2*pi*f*t + phase))`, `X = np.fft.rfft(x)`, `mags = 2*abs(X)/N` with `mags[0] /= 2`. Frequencies are integers (whole cycles per window) so there is **no spectral leakage**: peaks are exact. `peaks` = bins `k >= 1` with `mags[k] > 0.05 * mags.max()`. Return a small dataclass with `t, x, freqs (0..N/2), mags, peaks`.
Facts: `peak` for each peak (freq, amplitude rounded to 3 decimals); `range` of `x`; `domain` = `"frequency"` with text `"signal_spectrum draws the signal over time and its frequency spectrum"`; `domain = "frequency"` as the ClassVar.
Expected values (computed with numpy for this design; assert them):
- waves (3, 1.0, 0.0) + (5, 0.5, 0.0): peaks (3, 1.0), (5, 0.5); x range -1.386 to 1.386.
- wave (4, 1.0, 0.5): peaks (4, 1.0); x range -1.0 to 1.0.
- waves (2, 2.0, -1.0) + (7, 1.0, 3.0): peaks (2, 2.0), (7, 1.0); x range about -2.977 to 2.928.
Also test: duplicate frequencies rejected; 5 waves rejected; freq 0 and 41 rejected; `facts` agrees with `_data` (peaks list equals `[f for f, a in waves]`).
Accept: `python -m pytest -q tests/test_signal_spectrum.py`. Not registered yet, so `tests/test_registry.py` and the COMPONENTS.md sync test must still pass untouched.

## V3b  `signal_spectrum`: drawing and registration

Files: `components/signal_spectrum.py` (play), `components/registry.py`, `docs/COMPONENTS.md`, `tests/test_component_play_smoke.py`, `tests/conformance/signal_spectrum.json` + `tests/conformance/expected.json` (count these two as one). 5 files.

`play()` layout, using the same helpers the other charts use (`prepare`, `Clock`, `fit_in_room`, `caption_band_top`; read `bar_chart.py` for the caption-band pattern): top half the time-domain curve (axis labelled "Time"), bottom half the spectrum as bars at the integer frequencies with the frequency number under each peak bar and the axis labelled "Frequency (cycles per window)". Animation: curve draws left to right, then the bars grow. `show="time"` or `"spectrum"` draws only that half, full height. Duration `5.0` seconds for `both`, `3.5` for one panel. Coordinates come from `_data`; **no number on screen is typed by hand**. On any drawing exception degrade with `text_card` like `graph.py` does.
Follow the pattern of commit eb9e15f for registration, COMPONENTS.md and conformance. The COMPONENTS.md sync test must pass.
Accept: `python -m pytest -q tests/test_component_play_smoke.py tests/test_registry.py tests/test_conformance.py tests/test_signal_spectrum.py`, plus one real render of the first fixture (waves 3 and 5) with `animatica make --from <storyboard.json> --out /tmp/v3b`; **extract a frame** (the repo has `preview_frame`; use it) and look at it. State in the report what you see (curve, two bars at 3 and 5, labels readable, nothing under the caption). If rendering is impossible in your sandbox, say "render: unverified" and the owner or Claude will look.

## V3c  Steering the model to the engine

Files: `src/animatica/ai/prompt.py` (catalogue hint), `src/animatica/ai/template.py` (keyword rule so the template provider can pick it), `tests/reference_prompts.txt`, `tests/test_reference_prompts.py`, `tests/test_ai_prompt.py`. 5 files.

- Catalogue hint for `signal_spectrum`: `"sum of up to 4 sine waves drawn over time plus their frequency spectrum; use it for Fourier, frequency, harmonics, signals, 'two tones'; never use graph or array_viz to show a frequency spectrum"`.
- Template rule keyword `"fourier"`, `"frequency"`, `"harmonic"` -> `signal_spectrum`, with an example prompt and params; put it **before** the generic rules (rules are first-match, see the comment at the top of the rules list).
- Add the Fourier prompt to `tests/reference_prompts.txt` and make the existing reference-prompt test pass.
- With V1d active, wording such as "frequency domain" now has a component that may use it; confirm the claims message tail changes to `use signal_spectrum` (test in `tests/test_ai_prompt.py` or `tests/test_verify_claims.py`; if you edit the latter it is a sixth file: stop and ask).
Accept: `python -m pytest -q tests/test_ai_prompt.py tests/test_reference_prompts.py tests/test_template.py`, then the whole suite and `ruff check`.

**V3 done: stop. The owner runs the real Fourier prompt with `nim` and sends the `report.json` and video; Claude reviews.**

---

## Later (not for this batch)

V4 more engines one PR each (`complexity_race`, `sort_trace`, `growth_curve`, `probability_sim`), V5 narration from facts, V6 evaluation with the owner's provider keys. Cards will be written after V3 is reviewed.

## Hand-over checklist for the owner

1. Give opencode the prompt in `docs/handoffs/2026-11-17-opencode-start.md` and one card at a time.
2. After each card: `git am` the patch on `dev`, run the card's acceptance line, send Claude the report.
3. `dev` goes to `main` only after Windows CI is green (design section 6).

# Compute-and-verify: local code owns the numbers, the drawings and the checkable claims

Date: 2026-11-16 · Branch: `dev` (from `main` @ `44c838a`) · Status: draft for owner approval

Replaces `2026-11-16-stage-component-design.md` as the next piece of work. That document is
kept, marked deferred: the owner looked at real renders (854x480, Game Icons silhouettes) and
judged the icon look not good enough yet.

## 1. Why this exists

On 2026-11-16 a real run (`nim`, "Explain the Fourier transform...") produced a clean 59 s
video that was wrong in three places, and nothing in the program noticed:

- the caption "Frequency domain shows two peaks" sat over a plot of the *time-domain* signal;
- the narration repeated it ("the same signal appears as two distinct peaks");
- an `array_viz` of `1 0 -1 0 1 0 -1 0` was captioned "Superposition".

The model invented the numbers, the picture and the words independently. The owner's
direction: **rely less on the model, do the checking in programs, fix what can be fixed, send
the rest back.** The rule this design follows:

> The model decides *what to explain* and *how to say it*. Local code owns every number, every
> drawing coordinate and every claim that can be checked. A claim that cannot be checked is
> labelled unchecked, never presented as verified.

## 2. Goals, non-goals, anti-goals

**Goals**
1. On computable topics (functions, signals, algorithms, growth, probability, geometry), no
   number on screen or in speech that the code did not compute or confirm.
2. Each beat's component can report **facts** about what it draws (peaks, ranges, extrema,
   totals, ratios, sortedness). Facts are computed, not asserted by the model.
3. Captions and narration are checked against those facts and against the params.
4. A fixed policy for every failed check: fix silently if mechanical, send back to the model
   with the computed facts if it needs judgment, drop or degrade if it still fails.
5. A few **engine** components whose drawn data comes from a handful of parameters through
   real computation, starting with a signal/spectrum engine (the failing case).
6. Every run states what was checked and what was not (`report.json` and a console line).
7. Python only, offline, no new heavy dependency, fast (well under a second per storyboard).

**Non-goals**
- Proving real-world facts (science, history, economics). No local program can; see section 3.
- Replacing the model's writing. It still writes captions and narration.
- The icon stage (deferred) and a second renderer. Rust or Go: the checks are cheap, the cost
  is rendering and model calls, so a second language buys nothing.

**Anti-goals (a failure even if it "works")**
- A "verified" label on something that was not checked. Honesty about limits is the product.
- Silently changing the meaning of what the model wrote.
- Over-rejecting: a checker with many false positives makes more videos fail than the bugs
  it prevents. Default strictness is warn, not block (open decision 8.2).
- Changing storyboard v1 so existing `--from` files stop loading.

## 3. What can and cannot be checked

| Kind of claim | Checkable locally? | Handling |
|---|---|---|
| Maths: functions, identities, Big-O ratios, "two peaks", sums, sortedness | Yes (the existing safe function parser + numpy) | Compute, compare, fix or send back |
| Numbers in captions and narration | Yes, against params and facts | Ungrounded number = error |
| Structure: words that name something the component does not draw | Partly (heuristic, see 5.3) | Warn, drop narration, or send back |
| Layout: clipping, overlap, caption space | Yes (already partly in lint and frame-lint) | Fix automatically |
| Real-world facts ("vaccines train the immune system") | **No** | Marked unchecked; never "verified" |

## 4. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | **Verify after:** keep the model writing the whole storyboard; run checkers on it. | Covers all 35 existing components quickly. It can only reject or patch; it cannot make a missing visual appear. |
| B | **Compute first:** the model picks an engine and parameters; code computes data, facts and drawing; narration is limited to the facts. | The picture cannot lie. Each engine is real work, so it covers few topics. |
| C | Fully scripted templates, no model text. | Cheapest to verify, far too narrow for "any topic". |

Pick: **A first, then B for a few high-value engines.** A is a quick, broad win and builds the
facts machinery; B reuses it. C is rejected for breadth.

## 5. The design

### 5.1 Facts

A component may implement `facts(p) -> list[Fact]`, a pure function of params (no Manim). A
`Fact` is `{kind, subject, value, text}`, for example for `graph` with `fn="sin(x)+0.5*sin(3*x)"`:
range, zeros, local maxima and minima positions, whether the curve is clipped by `y_range`.
For `bar_chart`: max, min, total, ratio of largest to smallest. For `array_viz`: whether the
final state is sorted. For `stat_callout`: the parsed value. Components without `facts` are
simply unchecked beyond number grounding. **A component that gets `facts` must compute them
from the same pure data function its `play()` draws from** (for example `_data(p)` returning
the curve points or bar heights), never from a second copy of the logic, so facts cannot drift
from the picture. A test per such component calls `_data` and `facts` and asserts they agree.

### 5.2 Number grounding (the first check)

**What counts as a number:** digit strings (with commas, decimals, a percent sign or an `x`
suffix) and the number words zero to twenty plus hundred, thousand, million. Symbolic orders
such as "N squared" or "N log N" are handled by the claim patterns in 5.3, not here. A small
allowlist of free words ("one", "two", "first", "second" as ordinals or pronouns) is never
flagged.

**What grounds a number:** the same beat's params and facts, plus the params and facts of the
beat's earlier beats in the same scene (re-stating a figure is not inventing one) and the
storyboard title. **Earlier captions and narration never ground anything**, so an invented
figure in beat 1 cannot launder its repeat in beat 3.

**What this does and does not prove:** it is a *consistency* check between words and what is
drawn. For a model-written param (a `stat_callout` value) it only shows caption and screen
agree, not that the figure is true. For an engine, whose numbers are computed (5.5), it is a
real check. The report says which kind each check was.

This is cheap, high precision, and catches invented figures regardless of topic.

### 5.3 Claim checks

- **Structured claims (when a component supports them):** engine params carry what the beat is
  about (for example `peaks`), so the claim is exact.
- **Pattern claims (v1, deliberately small):** a few high-precision patterns over caption and
  narration: peak/peaks, increases/decreases, largest/smallest, "N squared", "N log N",
  "faster", equal/same. Each maps to a fact. Unknown phrasing is not checked, not guessed.
- **Domain mismatch:** each component declares which domains it can draw (a `domain` fact,
  default "plain axes"). Only a spectrum-capable component declares "frequency". Wording such as
  "frequency domain" or "spectrum" over any other component is an error. Until the
  `signal_spectrum` engine exists, such wording always fails and the repair prompt tells the
  model that no available component draws a frequency spectrum. This is how the Fourier
  `graph` beat is caught: by the domain rule, not by counting peaks. The time-domain wave
  `sin(x)+0.5*sin(3*x)` actually has **three** local maxima, and peak counting is wired only
  against `signal_spectrum` peak facts (a graph's maxima are `extremum` facts, never peak
  facts), so a peak count cannot be what catches a `graph` beat.
- **Not covered before V3/V4:** the `array_viz` "Superposition" beat. No listed pattern or
  fact says that `1 0 -1 0 ...` is not two waves adding up. It is out of scope for V1 and V2
  and is a stated reason for the engines.

### 5.4 The loop and its policy

```
generate -> existing lint -> verify -> mechanical fixes -> still failing? -> repair prompt
        -> (max 2 retries) -> still failing? -> drop the claim / degrade -> record in report
```

| Outcome | Examples | Action |
|---|---|---|
| Pass | numbers grounded, claims match facts | nothing |
| Autofix | curve clipped by `y_range`; stat value formatted differently from its fact | change params; record it |
| Send back | ungrounded number; "two peaks" but facts say one; identity does not hold | repair prompt containing the **computed facts** and the failing sentence |
| Degrade | still wrong after retries | blank the narration (speak the caption), or drop the claim; text-card fallback as a last resort |
| Unchecked | no pattern, no facts | listed in the report |

The repair prompt is the existing `repair.py` mechanism with a facts block added, so a weak
model gets "the code computed X; you wrote Y" rather than a vague complaint.

**Severity, stated once.** The send-back loop is **on by default**: it costs nothing on a
clean storyboard and at most 2 extra model calls for each failing scene. "Warn, not block"
describes only the **end state after the retries**: a failure that survives is a warning in
the report and on the console, and the run still renders. `--strict` turns surviving failures
into a non-zero exit. `--no-verify` turns the whole layer off (V1 ships checks as warnings
only, with no loop; V2 adds the loop).

**What the storyboard does.** The post-fix storyboard is the one written to `storyboard.json`
in the output folder, and every change is recorded in `report.json` as before and after, so a
`--from` re-run gives the same result (fixes are deterministic and idempotent). An empty
`narration` is already valid in storyboard v1 (the default is `""`), so "blank the narration"
needs no schema change. Captions are never rewritten by the code: a caption that still fails
after the retries is left as written, listed as failed, and the run warns. Text-card fallback
is the existing `fallback_text()` path and is used only when a component cannot draw.

### 5.5 Engines (phase 2)

First candidates, picked because truth is computable and ELI5 value is high (the builder
trims and orders them; the list is a proposal):

1. `signal_spectrum`: sum of sinusoids (frequency, amplitude, phase) drawn in time, then the
   FFT magnitude drawn as bars. Facts: peak frequencies and amplitudes. This repairs the
   failing Fourier case and is the first engine.
2. `complexity_race`: N, N log N, N squared counts computed for chosen N, drawn as bars/lines.
3. `sort_trace`: runs an actual sort and animates the real swaps (replaces trusting the model's
   steps).
4. `growth_curve`: compound growth / inflation computed from a rate and a start value.
5. `probability_sim`: seeded Monte Carlo giving a histogram; facts include the empirical mean.

Steering: when an engine exists for a topic, the component catalogue hint tells the model to
choose it over `graph` or `array_viz`, and the domain rule above is the backstop if it does not.

Each engine: small params, validated ranges, deterministic (seeded), computes its own data,
exposes `facts`, and draws through the existing helpers (caption band, safe area).

### 5.6 Narration from facts (phase 3, optional)

With `--narrate`, a second pass gives the model the facts sheet and asks for narration that
uses only those facts. The same grounding check then runs on the result. Costs one more model
call per scene, so it is opt-in.

### 5.7 Reporting

**Unit of a check:** one number looked at, or one claim-pattern match, counts as one check;
the same sentence can produce several. `report.json` gets a `verification` block: counts of checked, passed, fixed, sent back, and an
`unchecked` list of sentences nobody could check. The console prints one line, for example
`Verified 7 claims, fixed 1, 2 unchecked (see report.json)`. There is no "true" badge.

### 5.8 Code layout

New package `src/animatica/verify/`: `facts.py` (`Fact`, registry of `facts` providers),
`numbers.py` (grounding), `claims.py` (pattern table), `fix.py` (mechanical fixes), and the
loop wired into `pipeline.py` after the existing lint. Engines live in `components/`. All of
it is importable and testable without Manim.

## 6. Delivery

All on `dev`. Each phase is its own branch off `dev` and its own PR into `dev`. `dev` goes to
`main` only after Windows CI passes. Nothing lands on `main` directly.

| Phase | Scope | Done when |
|---|---|---|
| V1 | `Fact`, `facts()` for `graph`, `bar_chart`, `stat_callout`, `array_viz`; number grounding; the domain rule; `report.json` block; checks as warnings, no loop | Unit tests without Manim. A constructed storyboard with an invented figure and one with "three peaks" over a two-maxima graph each warn. The 2026-11-16 Fourier storyboard warns on the domain rule for its `graph` beat and its narration (not on the `array_viz` beat, see 5.3) |
| V2 | Mechanical fixes + repair prompt with facts + loop in the pipeline | A deliberately wrong storyboard is fixed or sent back and ends clean |
| V3 | `signal_spectrum` engine | Fourier prompt renders a real spectrum; facts match the drawing in a test |
| V4 | More engines (5.5), one PR each | Each has facts, reference prompt, conformance entry |
| V5 | Narration from facts | Optional flag; grounding check on its output |
| V6 | Eval: the Fourier prompt plus 20 varied prompts, run with the owner's own provider keys | Report in `docs/`. A false positive is a flag the owner marks as wrong when reading the report. Proposed targets: the Fourier run ends with no unsupported claim; at most 1 false positive per 10 videos; every miss listed |

## 7. Left to the builder

Exact fact kinds per component; the pattern table's contents; allowlist of free numbers;
engine order and parameter limits; strictness plumbing (`--strict`); where fixes are recorded;
test layout; how number words are parsed.

## 7b. Calls made after the builder review (check these while reading)

A fresh reviewer read this document and asked six questions. None needed the owner; each is
answered above and listed here so they can be overruled:

1. **Number grounding:** digits and number words zero to twenty plus hundred/thousand/million;
   grounded by the same beat, earlier beats' params and facts, and the title; earlier captions
   never ground (5.2). It is a consistency check, not truth, and the report says so.
2. **Fourier acceptance:** the domain rule catches the `graph` beat; peak counting would not
   (the wave has **three** maxima, and peak counting applies only to `signal_spectrum`
   peak facts -- a `graph` beat's maxima are `extremum` facts). The `array_viz` "Superposition" beat is explicitly not caught
   until the engines (5.3, V1 row).
3. **Warn versus loop:** the loop is on by default, "warn" means the end state after retries,
   `--strict` fails, `--no-verify` disables (5.4).
4. **Mutation:** the written `storyboard.json` is the post-fix one, fixes recorded with before
   and after, captions never rewritten, empty narration already valid (5.4).
5. **Facts vs drawing:** one shared pure data function per component, with a test (5.1).
6. **Steering to engines:** catalogue hint plus the domain rule as backstop (5.5).

Also settled: a check is one number or one pattern match; V6 false positives are marked by
the owner; proposed V6 targets are in the table.

## 8. Open decisions (owner's)

1. **sympy or not.** The existing safe parser plus numpy covers v1 and adds no dependency.
   sympy would allow symbolic identity checks (for example `a^2 + b^2 = c^2` rearrangements)
   at the cost of a heavy install. Default proposed: no sympy yet.
2. **Default strictness:** warn only (proposed), or block rendering on ungrounded numbers.
3. **Whether to add an optional `claims` field to beats** (additive, like `narration`) so a
   model can state exactly what a beat asserts. Proposed: not in v1; engine params carry it.
4. **Engine priority** after `signal_spectrum`.

## 9. Known unknowns

- False-positive rate of the pattern claims; V6 measures it.
- Whether free-tier models fix a beat from a facts-based repair prompt as reliably as from a
  schema error.
- How many ELI5-style topics fall in the computable set; the engines cover maths-flavoured
  topics, and the rest stay unchecked until another approach exists.

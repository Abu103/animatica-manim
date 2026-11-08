# HyperFrames backend (M1, experimental)

Status: **step 3 of 4 complete on `exp/hyperframes-3sat-pilot`-derived work.** Not merged,
not pushed. Step 4 is a visual acceptance render, which needs a machine with Chrome
and ffmpeg.

## Why this exists

The two hand-authored pilots proved the visual language but failed twice in the same
way: layout and timing were computed *inside* the renderer.

- 3-SAT pilot: a contradictory FALSE-case outro, fixed only in the template's JS, with
  no test able to catch a regression (all 42 tests never open `template.html`).
- Binary-search pilot: range bands positioned from `cell.offsetLeft` while the band's
  containing block is the stage, so every outline sits 80 px left of its cells; and
  cue times hard-coded (`stepStart = 6.0`, `stepDuration = 4.5`, notes at 5.6/9.3/13.3/
  17.3) while both fixtures need only three steps.

Both are the same defect: geometry and time lived in the renderer, where nothing
without a browser could test them. This backend moves both into validated Python.

## Architecture

```
storyboard.json (validated model data)
        |
   plan.py      -> Plan: absolute start/duration per beat, pixel rect per text line,
        |           deterministic text wrapping. Pure Python. Unit-tested.
   compose.py   -> index.html: numbers into data-*/style attributes, text as escaped
        |           text nodes. Byte-identical for identical input. Unit-tested.
   backend.py   -> `hyperframes render` in a child process, output captured.
```

Guarantees that are tested (`tests/test_hyperframes_{plan,compose,backend}.py`, 54 tests,
no Node/browser/Manim needed):

| Guarantee | Test |
| --- | --- |
| Beat times come from `component.duration()`, never invented | `test_duration_matches_component_and_conformance_corpus` |
| No text line leaves the safe area or overlaps another | `problems()` + its tests |
| Caption band respected; `--no-captions` reclaims the space | `test_caption_is_placed_in_the_caption_band`, `test_no_captions_removes_the_caption_band` |
| 8 long steps shrink instead of overflowing; impossible text fails with advice | `test_eight_long_steps_compress…`, `test_unfittable_steps_raise…` |
| Hostile storyboard text cannot become markup or code | `test_hostile_text_is_escaped_everywhere` (parsed with `html.parser`) |
| Storyboard text never appears inside a `<script>` body | `test_storyboard_text_never_reaches_the_script_block` |
| Composition cannot reach the network | `test_no_network_references` |
| Same storyboard → identical bytes and hash | `test_composition_is_byte_identical_across_calls` |
| Unsupported component fails before any subprocess runs | `test_unsupported_component_fails_before_the_cli_runs` |
| CLI failure shows the tail of its real output | `test_cli_failure_shows_the_tail_of_its_output` |

## Running it

```bash
npm install -g hyperframes@0.9.19          # or set ANIMATICA_HYPERFRAMES=/path/to/cli
animatica make --from docs/gallery/howto.json --backend hyperframes -o out/hf
```

Only `title_card`, `equation` and `steps_list` are supported. Anything else raises
`PlanError` naming the supported components and pointing at `--backend manim`, *before*
a subprocess is started.

## Verified on this branch (Linux sandbox, no browser)

- 54 unit tests pass; the existing suite was not run here (no `manim`).
- Real CLI (`hyperframes@0.9.19`) lint of a generated composition:
  **0 errors, 2 warnings** (down from 1 error, 4 warnings before the font/id/clip fixes).
- `hyperframes render` accepts the composition and starts encoding (`24fps · 2 workers`)
  before failing on `Chrome not found` — this sandbox cannot download
  `chrome-headless-shell`.

## Not verified

- **Any pixels.** No frame has been looked at. Motion, contrast and layout sampling in
  `hyperframes check` all need a browser, so they report 0 samples here.
- Windows, and the `npx --no-install` fallback path (only the `ANIMATICA_HYPERFRAMES`
  override and a PATH lookup were exercised).

## Security boundary

The model writes storyboard JSON only. It never writes HTML, CSS or JS, so no model code
is executed:

- Text reaches the document as escaped text nodes (`html.escape`), never inside
  `<script>`, an attribute value, a CSS value or a URL.
- Geometry, timing and colour tokens are numbers and whitelisted identifiers; an unknown
  colour token raises instead of being rendered.
- The template is tracked source with no `http(s)://`, no `@import`, no `src=` and no
  event-handler attributes.
- The CLI runs as a child process with `cwd` set to the composition directory.

If model-authored p5/JS is ever wanted, that needs a separate sandboxed origin with no
network and resource limits — escaping is not a sandbox.

## Known gaps and open decisions

| Item | Decision needed |
| --- | --- |
| Equations render as plain text (`latex_to_plain`) | Pin KaTeX locally (no CDN, as the pilots do for GSAP) or keep `equation` on Manim |
| Typography is DejaVu/system fonts; Manrope/Space Grotesk were dropped because naming a font without `@font-face` is a lint **error** | Bundle the SIL OFL `.woff2` files and emit `@font-face` |
| 2 remaining lint warnings: `nested_structure_needs_subcomposition` | Either flatten each text line into its own top-level clip, or move beats into sub-compositions mounted with `data-composition-src`. Settle it with a browser, not blind |
| No GSAP; the template exposes a GSAP-shaped `seek/time/progress` timeline | Confirm HyperFrames' seek contract on a real render before adding effects |
| `--vertical` refused with a clear error | Add a 9:16 variant of the layout constants |
| `equation` plain text ignores `mode: transform` | Implement when math typesetting lands |

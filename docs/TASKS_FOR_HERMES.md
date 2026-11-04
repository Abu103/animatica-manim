# Task cards for weak/free models (Hermes + Nemotron)
Rules: one card at a time. Do NOT touch files not listed. Run the acceptance command. If it fails twice, stop and write what failed at the bottom of docs/SESSION_TASKS.md.
Setup: `pip install -e . && animatica doctor && pytest -q` must pass first (206 passed, 20 render-skipped in a manim-less sandbox). Agent guide: `skills/animatica/SKILL.md`.
Pattern to copy: `src/animatica/components/bounce_sequence.py` (Params model, duration(), fallback_text(), play()), registry line in `components/registry.py`, doc row in `docs/COMPONENTS.md`, test in `tests/`, conformance JSON in `tests/conformance/` + entry in `expected.json`.

## T1 number_line  [DONE 2026-11-04 by agent session; render check pending on a manim machine]
Params: title, start, end, marks[] (optional), jump_from/jump_to pairs. Show a line, ticks, arrows jumping. Duration 2.0 + 0.7 s per jump.
Files: components/number_line.py, registry.py, docs/COMPONENTS.md, tests/test_number_line.py, tests/conformance/number_line.json, expected.json.
Accept: `pytest -q tests/test_number_line.py` and `animatica make --from tests/conformance/number_line.json -o /tmp/nl --quality preview` prints no Warning.

## T2 recursion_tree
Params: title, fn ("fib"), n (2..6). Draw the call tree F(n) -> F(n-1), F(n-2), highlight repeated calls in red. Cap nodes at 31.
Accept: same pattern; no overlapping nodes (use tidy-tree x positions, leaves evenly spaced).

## T3 array_viz
Params: title, values[2..12], steps[] each {highlight:[idx], swap:[i,j]}. Boxes with values, animate swaps. Duration 2.0 + 0.8 per step.

## T4 table  [DONE 2026-11-04 by agent session; render check pending on a manim machine]
Params: title, columns[], rows[][] (max 6x6). Rows fade in one by one.

## T5 timeline
Params: title, events[{label, text}] (max 8). Dots on a line, labels alternate above/below.

## T6 compare
Params: title, left{heading, bullets[]}, right{...}. Two columns, bullets fade in alternately.

## T7 log scale for bar_chart  [DONE 2026-11-04: scale param landed via P0.2]
Add param `scale: "linear"|"sqrt"|"log"` (default linear) to bar_chart.py. Heights use scale, labels show real values, min height 0.08 so tiny bars show. Tests: heights monotonic, labels unchanged.

## T8 reference prompts
Add 15 diverse prompts to tests/reference_prompts_eval.txt (not the existing file). Each one line, covering each component. No code.

## T9 new-component scaffold  [DONE 2026-11-04: `animatica new-component NAME`, tests/test_scaffold.py, e2e verified]
`animatica new-component NAME` writes the files listed in the pattern above with TODOs. Test: run it in a tmp dir, files exist, pytest collects them.

Log every finished card in docs/SESSION_TASKS.md with date and result.


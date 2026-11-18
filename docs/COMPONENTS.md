# Animatica Components

This document lists every registered component in Animatica v1. It is kept in
sync with the code: the test suite compares this document against
`default_registry().names()`, so adding a component requires updating both.

## Components

| Component | Params (summary) | Duration |
|-----------|------------------|----------|
| `title_card` | `title`, `subtitle` | 3.0 s |
| `equation` | `mode` (reveal/transform), `latex[]` (1-6) | 2.0 s + 2.0 s per extra step |
| `steps_list` | `items[]` (1-8) | 1.5 s per item + 1.0 s |
| `graph` | `fn`, `x_range`, `y_range`, optional `approx_fn` (a second curve), optional `label`, optional `approx_label` | 4.0 s |
| `bar_chart` | `title`, `labels[]`, `values[]` (1-12) | 2.0 s + 0.3 s per bar |
| `shape_morph` | `from_shape`, `to_shape`, `from_color`, `to_color` | 3.0 s |
| `diagram` | `nodes[]` (2-10), `edges[]` | 1.0 s + 0.6 s per edge |
| `code_highlight` | `code` (<=1200 chars), `language`, `lines[]` | 3.0 s + 1.0 s per line |
| `number_line` | `title`, `start`, `end` (`end` must be > `start`), `marks[]` (<=12, inside range), `jumps[]` (<=8, each `[from, to]` inside range) | 2.0 s + 0.7 s per jump |
| `matrix` | `title`, `values[][]` (max 6x6), optional `highlight[][]` ([row,col] pairs) | 2.0 s + 0.4 s per cell |
| `stat_callout` | `value`, `label`, optional `delta` | 3.0 s fixed |
| `formula_derivation` | `title`, `steps[]` (1-6), optional `highlight[]` | 2.0 s + 1.0 s per step |
| `parametric_graph` | `title`, `x_expr`, `y_expr`, `t_range[]`, optional `label` | 4.0 s fixed |
| `code_walkthrough` | `title`, `code`, `language`, optional `lines[]`, `variables{}` | 3.0 s + 1.0 s per line |
| `flow` | `title`, `nodes[]` (1-10), `edges[][]` ([from,to] pairs) | 2.0 s + 0.6 s per edge |
| `table` | `title`, `columns[]` (1-6), `rows[][]` (1-6 rows; every row needs exactly `len(columns)` cells) | 2.0 s + 0.5 s per row |
| `recursion_tree` | `title`, `fn` (only `"fib"`), `n` (2..6) | 2.0 s + 0.8 s per level of `n` (tree capped at 31 nodes) |
| `array_viz` | `title`, `values[]` (2-12), `steps[]` (<=12); a step carries `highlight[]`, `swap` (exactly 2 indices), and/or binary-search `low`/`high`/`mid` — all indices in `[0, len(values)-1]`, `low` <= `high`, `mid` inside that range | 2.0 s + 0.8 s per step |
| `timeline` | `title`, `events[]` (1-8), each `{label, text}` (both keys required) | 2.0 s + 0.8 s per event |
| `compare` | `title`, `left` and `right`, each `{heading, bullets[]}` (1-6 bullets per side) | 2.2 s + 0.6 s per bullet (both sides) |
| `probability_tree` | `title`, optional `root` (default "Start"), `branches[]` (1-3), each `{label, p, children[]}` (<=3 `{label, p}` each); `0 < p <= 1`, siblings must sum to 1, labels <=40 chars | 2.0 s + 0.5 s per node |
| `venn` | `title`, `sets[]` (2-3) of `{label, items[]}`, optional `shared[]` of `{of: [set indices], items[]}`; items <=14 chars, <=3 per region (3 sets: 1 per shared region of <=7 chars, <=2 per set) | 2.0 s + 0.7 s per set + 0.5 s per shared region |
| `pie_donut` | `title`, `slices[]` (2-6) of `{label, value > 0}`, optional `donut` (bool) and `center` (text in the hole, <=16 chars); slices under 3% are rejected (merge into "Other"); percents are whole numbers summing to 100 | 2.0 s + 0.5 s per slice |
| `code_diff` | `title`, `before`, `after` (full code text; the diff is computed; <=12 diff lines of <=48 chars; not syntax-highlighted) | 2.5 s + 0.5 s per changed line |
| `graph_traversal` | `title`, `nodes[]` (2-8 labels, <=4 chars), `edges[]` (pairs of labels, <=12), optional `start` (default first node), `order` (`bfs`\|`dfs`), `directed`; the visit order is computed, neighbours in `nodes` order | 2.5 s + 0.6 s per visited node |
| `unit_circle` | `title`, `angles[]` (1-4 special angles in degrees: multiples of 30 or 45 in [0, 360)), optional `units` (`degrees`\|`radians`); exact cos/sin are looked up, not typed | 2.5 s + 0.9 s per angle |
| `bounce_sequence` | `title`, `values[]` (2-20), optional `scale` (auto/linear/sqrt/log), `labels[]` (optional) | 2.0 s + 0.8 s per term |
| `signal_spectrum` | `title`, `waves[]` (1-4) of `{freq: 1-40 (distinct), amp: 0.1-5.0, phase: -3.2..3.2 (default 0)}`, optional `show` (time/spectrum/both, default both) | 5.0 s (both) / 3.5 s (one panel) |

Registered component names:
- title_card
- equation
- steps_list
- graph
- bar_chart
- shape_morph
- diagram
- code_highlight
- bounce_sequence
- unit_circle
- graph_traversal
- code_diff
- pie_donut
- venn
- probability_tree
- compare
- timeline
- array_viz
- recursion_tree
- table
- number_line
- matrix
- stat_callout
- formula_derivation
- parametric_graph
- code_walkthrough
- flow
- signal_spectrum

## Stability

The storyboard JSON is the stable contract. Components own layout, timing, and
self-degradation: a failed beat becomes a plain text card plus a warning and
never aborts the video. New components are added as one file plus one registry
entry (see the implementation plan in `docs/superpowers/plans/`).


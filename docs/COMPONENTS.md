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
| `graph` | `fn`, `x_range`, `y_range`, `label` | 4.0 s |
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
| `compare` | `title`, `left` and `right`, each `{heading, bullets[]}` (1-6 bullets per side) | 2.0 s + 0.6 s per bullet (both sides) |
| `bounce_sequence` | `title`, `values[]` (2-20), optional `scale` (auto/linear/sqrt/log), `labels[]` (optional) | 2.0 s + 0.8 s per term |

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

## Stability

The storyboard JSON is the stable contract. Components own layout, timing, and
self-degradation: a failed beat becomes a plain text card plus a warning and
never aborts the video. New components are added as one file plus one registry
entry (see the implementation plan in `docs/superpowers/plans/`).


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
| `number_line` | `title`, TODO | 3.0 s |
| `table` | `title`, TODO | 3.0 s |
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
- table
- number_line

## Stability

The storyboard JSON is the stable contract. Components own layout, timing, and
self-degradation: a failed beat becomes a plain text card plus a warning and
never aborts the video. New components are added as one file plus one registry
entry (see the implementation plan in `docs/superpowers/plans/`).


# Gallery

The storyboards in `docs/gallery/`, and the result of rendering each one for real. The MP4s
are not committed (large binaries); `scripts/render_gallery.py` makes them in `out/gallery/`,
and they get attached to a release by hand.

## What is in it

Hand-written storyboards (not model output):

| file | what it shows |
|---|---|
| `fibonacci.json` | title card, equation, and a bouncing-ball sequence through Fibonacci terms 0-15 |
| `pythagoras.json` | title card and a two-step equation reveal for the Pythagorean theorem |
| `sine.json` | title card and a graph of `sin(x)` over one period |
| `howto.json` | title card and a four-step list for boiling an egg |
| `matrix.json` | a 2x2 matrix with diagonal cells highlighted |
| `stat_callout.json` | a large percentage with label and delta |
| `formula_derivation.json` | step-by-step quadratic formula derivation |
| `parametric_graph.json` | a parametric circle x=cos(t), y=sin(t) |
| `code_walkthrough.json` | recursive Fibonacci function with variable panel |
| `flow.json` | water cycle process flow with 4 nodes |

Model outputs from the eval baseline, each with a still (`eval_*.png`). The prompts, numbers and
provider they came from are in [`EVAL_BASELINE.md`](EVAL_BASELINE.md):

| file | what it shows |
|---|---|
| `eval_taylor_series.json` | a Taylor polynomial against `sin(x)`, with the graph's legend |
| `eval_recursion_tree.json` | the `fib(5)` call tree |
| `eval_bar_chart.json`, `eval_number_line.json`, `eval_code_highlight.json` | one clean render each |

## Render them yourself

Needs a working install (see the README). No AI key is needed.

```
python scripts/render_gallery.py
```

One storyboard, without the script:

```
animatica make --from docs/gallery/fibonacci.json -o out/gallery/fibonacci --quality preview
```

The script exits non-zero if any render fails: `animatica make` exits non-zero, no `report.json`
is written, or a component fell back to a text card. Warnings do not fail a render; they are
listed verbatim below.

To paste a fresh run into this file (date, commit and machine included):

```
python scripts/render_gallery.py --write-doc
```

## Results

<!-- gallery-results:start -->

| | |
|---|---|
| Date | 2026-11-13 18:11 (local time, the machine below) |
| Commit | `e071c1707ddc2566ff00963f1ab81cb367e29fc7` |
| Machine | Windows 11, Python 3.14.10, Manim 0.22.1 |
| Command | `animatica make --from <file> -o out/gallery/<name> --quality preview` |

| storyboard | result | warnings | seconds |
|---|---|---|---|
| `code_walkthrough` | ok | 0 | 10.3 |
| `eval_bar_chart` | ok | 0 | 7.2 |
| `eval_code_highlight` | ok | 0 | 7.9 |
| `eval_number_line` | ok | 0 | 7.9 |
| `eval_recursion_tree` | ok | 0 | 11.7 |
| `eval_taylor_series` | ok | 0 | 16.2 |
| `fibonacci` | ok | 0 | 25.2 |
| `flow` | ok | 0 | 7.8 |
| `formula_derivation` | ok | 0 | 9.6 |
| `howto` | ok | 0 | 12.5 |
| `matrix` | ok | 0 | 7.7 |
| `parametric_graph` | ok | 0 | 8.6 |
| `pythagoras` | ok | 0 | 11.8 |
| `sine` | ok | 0 | 11.8 |
| `stat_callout` | ok | 0 | 7.8 |

15/15 rendered, 0 failed.

<!-- gallery-results:end -->

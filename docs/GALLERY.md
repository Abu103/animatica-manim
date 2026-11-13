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

No run recorded yet. Run `python scripts/render_gallery.py --write-doc` on a machine with Manim
and LaTeX installed; it replaces this paragraph with the real table.

<!-- gallery-results:end -->

# Eval baseline

The first measured run of the reference prompts against a live provider. Every
number below comes from one run of one provider; nothing here is estimated,
rounded or carried over from another run.

## The run

| | |
|---|---|
| Date | 2026-11-11, 12:57:16 - 13:02:15 (local time, this machine) |
| Commit | `1d6fbc6143e20c97c1a500ad1a629f4904af3160` (`tests: one reference prompt per registered component`, branch `hermes/m2-eval-baseline`, off `main` = `88652e2`) |
| Provider | `nim` (NVIDIA build.nvidia.com, key from `animatica setup`) |
| Model id | `nvidia/nemotron-3.5-super-vl-120b-a12b` (the model in `src/animatica/ai/providers.toml`) |
| Corpus | `tests/reference_prompts.txt` -- 21 prompts, one per registered component |
| Retries | `--max-retries 2` (the harness makes one call plus up to two repair calls) |
| Machine | Windows, Python 3.14.10, Manim 0.22.1 |

### The command

The stock command is

```
animatica eval --models <providerA>,<providerB> --prompts tests/reference_prompts.txt --max-retries 2
```

but it could not be run as written on this machine, for two reasons that are
worth recording rather than hiding:

1. **The eval CLI has no `--model` flag.** A provider takes its model from
   `ANIMATICA_MODEL` or from its default, so two providers in one process
   cannot have two different model ids. The baseline below therefore ran the
   same harness (`generate_storyboard` with the repair loop, `lint_storyboard`,
   the same `EvalResult` fields and the same formatters) with the model ids
   spelled out, through `out/t16_eval.py`.
2. **The configured default model ids of the second provider are retired.**
   `animatica eval --models groq ...` dies with

   ```
   ProviderError: groq: HTTP 404: {"error":{"message":"The model
   `llama-3.1-8b-instant` does not exist or you do not have access to it."
   ```

   and the openrouter default (`meta-llama/llama-3.1-8b-instruct:free`)
   answers `HTTP 404: This model is unavailable for free`.

## LIVE-MODEL OUTPUT

The table below is the output of that run, pasted as it was printed
(`out/t16_run_final.txt` holds the whole log).

### `format_multi_table`

```
prompt                                 nim
---------------------------------------------------------
array visualization of the values 5 3 ok
bar chart of sales by quarter         ok
code highlight the main function      ok
compare mitosis and meiosis side by sir2
derive the quadratic formula step by sok
diagram with nodes A B C and edges frook
explain taylor series                 r1
explain the pythagorean theorem a^2 + ok
explain this python function line by lr1
flow diagram from water to steam to tuok
make a title card about renewable enerok
matrix of the 3x3 identity matrix     ok
morph a circle into a square          ok
number line from 0 to 20 with jumps atok
parametric graph of a circle with x eqok
show the fibonacci series with a ball ok
show the recursion call tree of fib(5)ok
stat callout that 42 percent of studenok
steps to bake a cake                  ok
table of planets with diameter and masok
timeline of the history of computers  ERROR
---------------------------------------------------------
VALID/Total                           17/21 e1 (3 retry)
```

`ok` = valid on the first try, `r1`/`r2` = valid after one/two repair calls,
`ERROR` = never valid.

### `format_table` (the same run, per prompt)

```
provider       model                prompt                         first  eventual  retries warn  secs
nim            nvidia/nemotron-3.5-super-vl-120b-a12b make a title card about renewa yes    yes       0       0     3.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b explain the pythagorean theore yes    yes       0       0     7.8
nim            nvidia/nemotron-3.5-super-vl-120b-a12b steps to bake a cake           yes    yes       0       0    10.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b explain taylor series          NO     yes       1       0    14.5
nim            nvidia/nemotron-3.5-super-vl-120b-a12b bar chart of sales by quarter  yes    yes       0       0     3.2
nim            nvidia/nemotron-3.5-super-vl-120b-a12b morph a circle into a square   yes    yes       0       0     3.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b diagram with nodes A B C and e yes    yes       0       0     2.2
nim            nvidia/nemotron-3.5-super-vl-120b-a12b flow diagram from water to ste yes    yes       0       0     3.2
nim            nvidia/nemotron-3.5-super-vl-120b-a12b code highlight the main functi yes    yes       0       0     5.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b explain this python function l NO     yes       1       0     6.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b compare mitosis and meiosis si NO     yes       2       0     8.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b timeline of the history of com NO     NO        2       0     0.0    ERROR: failed to generate a vali
nim            nvidia/nemotron-3.5-super-vl-120b-a12b array visualization of the val yes    yes       0       0     6.4
nim            nvidia/nemotron-3.5-super-vl-120b-a12b show the recursion call tree o yes    yes       0       0     5.2
nim            nvidia/nemotron-3.5-super-vl-120b-a12b table of planets with diameter yes    yes       0       0     5.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b number line from 0 to 20 with  yes    yes       0       0     3.4
nim            nvidia/nemotron-3.5-super-vl-120b-a12b matrix of the 3x3 identity mat yes    yes       0       0     5.6
nim            nvidia/nemotron-3.5-super-vl-120b-a12b stat callout that 42 percent o yes    yes       0       0     3.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b derive the quadratic formula s yes    yes       0       0     8.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b parametric graph of a circle w yes    yes       0       0     4.0
nim            nvidia/nemotron-3.5-super-vl-120b-a12b show the fibonacci series with yes    yes       0       0    10.8

17/21 first-try valid, 3 retry-valid, 20/21 eventual valid, 1 errored
```

`warn` is the number of lint/guidance notes the storyboard produced: **0 for
every prompt that produced a storyboard.**

### What the numbers say

* **17 of 21 prompts (81%) were valid on the first try.** Every one of the
  21 components is reachable: the corpus reaches all 21 and the model used
  the component the prompt was about in every case that produced a storyboard.
* **20 of 21 (95%) ended up valid** after at most two repair calls.
* **One prompt failed outright**: `timeline of the history of computers`
  (three calls, all invalid). The same prompt succeeded on a later run, so
  this is the model's output, not a component that refuses to work.
* **Zero lint warnings.** The storyboards the model produced needed no
  repair from the linter (no redundant chart, no split sequence).

## The second provider: rate limited, and dropped

`groq` was tried as the second column and **is not part of the baseline**.
With the model id that the key can actually reach (`openai/gpt-oss-20b`; the
configured default is retired), the free tier answered **11 of the 21
prompts** before the run was stopped, with **19 HTTP 429 responses** in
between:

```
[groq] 'compare mitosis and meiosis side by side' -> rate limited (retry after 39.0), waiting 39s [108s]
[groq] 'compare mitosis and meiosis side by side' -> rate limited (retry after 7.0), waiting 7s [147s]
```

Every prompt that came back was valid (11 of 11, no retries needed) -- the
model is not the problem, the rate limit is. The partial result is recorded
here rather than rounded into a column.

## The gallery

Five of the successful storyboards were rendered with `--quality preview`.
The storyboard JSON, the MP4 and one still of each are in `docs/gallery/`
(the MP4s are not committed -- they are large binaries; the frames and the
storyboards are).

| file | prompt | component | why this one |
|---|---|---|---|
| `eval_taylor_series` | `explain taylor series` | `graph` with `approx_fn` | the graph's legend sits above the plot, the axis numbers clear of the caption |
| `eval_recursion_tree` | `show the recursion call tree of fib(5)` | `recursion_tree` | the call tree is the real parent-to-child relation |
| `eval_bar_chart` | `bar chart of sales by quarter` | `bar_chart` | clean, no warnings |
| `eval_number_line` | `number line from 0 to 20 with jumps at 0 7 15` | `number_line` | clean, no warnings |
| `eval_code_highlight` | `code highlight the main function` | `code_highlight` | clean, no warnings |

Two storyboards that the eval scored `ok` are **not** in the gallery because
the render is visibly broken: the Fibonacci bounce (its caption is printed
twice, issue #31) and the parametric circle (its axis numbers carry full
float precision, issue #32).

## What the run found (GitHub issues)

The prompts are also a bug hunt: four components misbehaved on model output
that no unit test had tried.

| issue | component | what it does |
|---|---|---|
| [#28](https://github.com/Abu103/animatica-manim/issues/28) | `array_viz` | runs 2.3 s longer than the duration it declares (the captions drift) |
| [#29](https://github.com/Abu103/animatica-manim/issues/29) | `formula_derivation` | draws its last step under the caption |
| [#30](https://github.com/Abu103/animatica-manim/issues/30) | `steps_list` | puts long items outside the 5% safe-area margin |
| [#31](https://github.com/Abu103/animatica-manim/issues/31) | caption | a caption too wide for the frame is printed twice, overlapping |
| [#32](https://github.com/Abu103/animatica-manim/issues/32) | `parametric_graph` | prints its axis numbers with full float precision |

## Not verified

* Only one provider is in the baseline; the second column was rate limited.
* The numbers are one run of one model at one temperature. The same prompt
  differs between runs (the `timeline` prompt failed here and succeeded
  minutes later), so treat the percentages as a measurement of this run, not
  as a stable property of the model.
* The gallery frames were judged by eye on this Windows box.
* Nothing is pushed: the branch is `hermes/m2-eval-baseline`, local only.

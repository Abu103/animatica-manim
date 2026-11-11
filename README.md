# Animatica

Describe something, get an explainer video. Built on Manim; works with free AI models.

## Install (Windows / Mac / Linux)

One command, same result on Linux, macOS and Windows. It installs Python, manim,
ffmpeg and LaTeX, and it solves the cairo/pango problem for you: on Linux it uses
the system packages when they exist and otherwise fetches a prebuilt bundle (no
manual downloads, no `apt` knowledge needed); on Windows the wheels already carry
the DLLs, so there is nothing to fetch. First run takes a few minutes because of
LaTeX; later runs are instant. Supported and CI-tested: **Linux** and **Windows**;
macOS is best-effort.

```
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.sh | bash

# Windows (PowerShell)
irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
```

You do not have to set environment variables, and you do not have to install
cairo or pango yourself: where they are needed the installer puts them in the
project folder and Animatica activates them on import. Windows PowerShell only:
if script execution is blocked, use
`powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1` from a clone.

When dependency checks pass, an interactive terminal automatically opens the
`animatica setup` wizard in the same session. Choose **template** for offline
starter examples, or choose an AI provider; cloud providers ask you to confirm
access and paste a key. There is no separate setup command to remember. In CI or
without a terminal, the wizard is skipped; set `ANIMATICA_SKIP_SETUP=1` to skip
it explicitly, then run the installed environment's `animatica setup` command
(the executable paths are shown below; replace `tui` with `setup`).

After setup, open the interactive studio (`animatica tui`). The installer keeps
Animatica inside its virtual environment, so use the environment's executable:

```
# Linux / macOS
"$HOME/animatica-manim/.venv/bin/animatica" tui

# Windows PowerShell
& "$HOME\animatica-manim\.venv\Scripts\animatica.exe" tui
```

The studio guides you through an idea, scenes, style, and rendering. The
non-interactive path, when you already know what you want, is:

```
animatica doctor                  # what is installed, what is missing
animatica doctor --fix --yes      # repair ffmpeg / LaTeX automatically
animatica make "graph of sin(x)" -o out/
```

LaTeX is optional: without it equations fall back to plain text and everything
else renders normally. `animatica doctor --fix` installs it later if you want it.

<details><summary>Manual install (if you prefer apt/pip)</summary>

```
sudo apt install libcairo2-dev libpango1.0-dev pkg-config ffmpeg   # Debian/Ubuntu
pip install -e .
animatica doctor --fix
```
</details>

## First video (no key needed)

```
animatica make "graph of sin(x)" -o out/
```

## Any prompt (needs a free AI key)

```
animatica setup
animatica make "explain the fibonacci series by making a ball bounce on terms 0 to 15" -o out/ --provider openrouter
```

Free options: OpenRouter, Groq, NVIDIA build.nvidia.com, or Ollama locally (no key). `--provider X --model <id>` picks a model.

## Gallery

Hand-written example storyboards (not model output), in `docs/gallery/`:
- `fibonacci.json` — title card, equation, and a bouncing-ball sequence through Fibonacci terms 0–15
- `pythagoras.json` — title card and a two-step equation reveal for the Pythagorean theorem
- `sine.json` — title card and a graph of `sin(x)` over one period
- `howto.json` — title card and a four-step list for boiling an egg
- `matrix.json` — a 2x2 matrix with diagonal cells highlighted
- `stat_callout.json` — a large percentage with label and delta
- `formula_derivation.json` — step-by-step quadratic formula derivation
- `parametric_graph.json` — a parametric circle x=cos(t), y=sin(t)
- `code_walkthrough.json` — recursive Fibonacci function with variable panel
- `flow.json` — water cycle process flow with 4 nodes

Re-render any one (no AI key needed):
```
animatica make --from docs/gallery/fibonacci.json -o out/
```

All ten render successfully with LaTeX installed (equations and graph axis numbers use real LaTeX; without LaTeX they degrade gracefully to plain text). Burned-in captions appear at the bottom of each video and may trigger `safe_area` frame-lint warnings — this is expected caption placement, not clipping.

Also in `docs/gallery/`: five **model outputs** from the eval baseline (`eval_*.json`, with a still of each):
- `eval_taylor_series` — a Taylor polynomial against `sin(x)`, with the graph's legend
- `eval_recursion_tree` — the `fib(5)` call tree
- `eval_bar_chart`, `eval_number_line`, `eval_code_highlight` — one clean render each

The prompts, the numbers and the provider they came from are in [`docs/EVAL_BASELINE.md`](docs/EVAL_BASELINE.md).

The rendered MP4s are not committed (they're large binary artifacts). To regenerate them all:
```
for f in docs/gallery/*.json; do
  animatica make --from "$f" -o "out/$(basename "$f" .json)" --preview
done
```

## Useful flags
`--quality preview` (fast), `--from storyboard.json` (re-render without calling a model), `--no-captions`, `--debug`.

## When something looks off
Warnings print in the terminal and go to `out/report.json`. The `out/storyboard.json` is plain JSON: edit it and re-render with `--from`.

More: `docs/GUIDE.md`, `docs/COMPONENTS.md`, roadmap `docs/ROADMAP.md`.


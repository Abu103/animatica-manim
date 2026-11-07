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

Then everything else happens in one place:

```
animatica tui
```

The studio is where you pick quality, theme, orientation and provider (arrow
keys, or just start typing to filter the list), paste an API key, and render.
Your job-step choices are remembered, so the next session starts where you left
off. The equivalent non-interactive path, when you already know what you want:

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


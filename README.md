# Animatica

Describe something, get an explainer video. Built on Manim; works with free AI models.

## Install (Windows / Mac / Linux)

One command sets everything up with full quality (real LaTeX + real ffmpeg). Expect a few minutes the first time (downloading LaTeX is the slow part); later runs are quick. Supported and CI-tested: **Linux** and **Windows**; macOS is best-effort.


```
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.sh | bash
# Windows
irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
```

How it stays fast: `uv` installs manim + the bundled static ffmpeg wheel (`imageio-ffmpeg`,
no winget/brew needed), and LaTeX comes from a pre-baked `tinytex-manim.zip` release asset
(no TinyTeX installer, no tlmgr). Equivalent manual path: `animatica bootstrap` / `animatica doctor --fix`.

Not sure it worked? Run `animatica doctor` (it lists what is missing and how to fix it); `animatica doctor --fix --yes` repairs what it can.

Manual equivalent:

```
1.  Install Python 3.10+ and ffmpeg      (Windows: winget install ffmpeg)
2.  pip install -e .
3.  animatica doctor --fix               (auto-installs ffmpeg + TinyTeX packages)
```

LaTeX is needed for nice equations. Install TinyTeX (yihui.org/tinytex), then **this one line**, then run `animatica doctor` again:

```
tlmgr install standalone preview babel-english amsmath amsfonts dvisvgm
```

Without it everything still works, equations just show as plain text.

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

Re-render one: `animatica make --from docs/gallery/fibonacci.json -o out/`

All six render successfully with LaTeX installed (equations and graph axis numbers use real LaTeX; without LaTeX they degrade gracefully to plain text). Burned-in captions appear at the bottom of each video and may trigger `safe_area` frame-lint warnings — this is expected caption placement, not clipping.

## Useful flags
`--quality preview` (fast), `--from storyboard.json` (re-render without calling a model), `--no-captions`, `--debug`.

## When something looks off
Warnings print in the terminal and go to `out/report.json`. The `out/storyboard.json` is plain JSON: edit it and re-render with `--from`.

More: `docs/GUIDE.md`, `docs/COMPONENTS.md`, roadmap `docs/ROADMAP.md`.


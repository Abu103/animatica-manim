# Animatica

Describe something, get an explainer video. Built on Manim; works with free AI models.

![demo](docs/gallery/fibonacci.gif)

## Install (Windows / Mac / Linux)

One command does everything in ~25-40s, full quality (real LaTeX + real ffmpeg), deps installed in parallel:

```
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.sh | bash
# Windows
irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
```

How it stays fast: `uv` installs manim + the bundled static ffmpeg wheel (`imageio-ffmpeg`,
no winget/brew needed), and LaTeX comes from a pre-baked `tinytex-manim.zip` release asset
(no TinyTeX installer, no tlmgr). Equivalent manual path: `animatica bootstrap` / `animatica doctor --fix`.

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
Hand-written example storyboards (not model output), in `docs/gallery/`: `fibonacci`, `pythagoras`, `sine`, `howto` (.json source + .mp4).
Re-render one: `animatica make --from docs/gallery/fibonacci.json -o out/`

## Useful flags
`--quality preview` (fast), `--from storyboard.json` (re-render without calling a model), `--no-captions`, `--debug`.

## When something looks off
Warnings print in the terminal and go to `out/report.json`. The `out/storyboard.json` is plain JSON: edit it and re-render with `--from`.

More: `docs/GUIDE.md`, `docs/COMPONENTS.md`, roadmap `docs/ROADMAP.md`.


# Animatica Beginner Guide

Welcome to Animatica. This guide walks you through installing and running your
first explainer video, assuming you have never used a terminal before.

## What this does

Animatica turns a plain-language prompt into a 3Blue1Brown-style explainer
video (MP4 + captions) with no Python or LaTeX knowledge required:

```
animatica make "explain the pythagorean theorem a^2 + b^2 = c^2" -o out/
```

It picks the right visuals (title card, equation, graph, bar chart, steps,
diagram, morph, code highlight), renders them with Manim, and encodes the video.

## What you need

- A computer (Windows, macOS, or Linux).
- Python 3.10 or newer (3.11 recommended).
- An internet connection for the one-time install (after that, template prompts
  work offline).
- About 15 minutes for the first install; later videos render in seconds.

## Install (fast, ~30 seconds)

One command, full quality, deps installed in parallel:

```
# Windows (PowerShell)
irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.sh | bash
```

It uses `uv` for Python deps, the bundled static ffmpeg (`imageio-ffmpeg`), and a
pre-baked TinyTeX zip — then runs `animatica doctor` to verify. If the TinyTeX
release asset is unavailable it falls back to `animatica doctor --fix`.

### Manual install

### Windows
1. Install Python 3.11 from python.org. During install, check both boxes:
   **"Add Python to PATH"** and **"Install py launcher for all users"**.
2. Open PowerShell and run:
   ```
   py -3.11 -m pip install manim==0.22.1
   winget install ffmpeg
   ```
   You can also run Python modules directly with `py -m pip <command>`.
3. Install TinyTeX from https://yihui.org/tinytex/ (for LaTeX equations).

### macOS
1. Install Homebrew if you don't have it (brew.sh).
2. Run:
   ```
   brew install cairo pango ffmpeg mactex
   pip install manim==0.22.1
   ```

### Linux (Ubuntu/WSL)
1. Run:
   ```
   sudo apt install libcairo2-dev pkg-config libpango1.0-dev clang build-essential texlive texlive-latex-extra ffmpeg
   pip install manim==0.22.1
   ```
   If `apt` is interrupted, run `sudo dpkg --configure -a` first.
2. If `kpsewhich standalone.cls` returns nothing, run `mktexlsr`.

## Install Animatica itself

1. Copy the `animatica-v1` folder to your machine.
2. Open a terminal in that folder.
3. Create a virtual environment (Python 3.11):
   ```
   py -3.11 -m venv .venv        # Windows
   python3.11 -m venv .venv      # macOS/Linux
   ```
4. Activate it and install Animatica:
   ```
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # macOS/Linux
   pip install -e .
   ```
5. Verify: `animatica --version` should print `animatica 0.1.0`.

## Virtual environment

A virtual environment (`.venv`) keeps Animatica's packages separate from your
system Python so installs never conflict. Activate it each time you open a new
terminal before running `animatica`.

## Run animatica doctor

`animatica doctor` checks every dependency and tells you exactly what to fix:

```
animatica doctor
```

Each line shows OK or FAIL plus a one-line fix. Run it after install and
whenever a video fails to render.

## Your first video

```
animatica make "explain the pythagorean theorem a^2 + b^2 = c^2" -o out/
```

This writes `out/video.mp4` and `out/captions.vtt`. Open `video.mp4` to watch.

## Writing good prompts

Animatica matches your prompt to templates when possible. Good prompts:

- "make a title card about my topic"
- "explain the pythagorean theorem a^2 + b^2 = c^2"
- "graph of sin(x)"
- "bar chart of sales by quarter"
- "steps to bake a cake"
- "morph a circle into a square"
- "flow diagram from a to b"
- "walk through this python code"

Avoid vague prompts like "make a video about science" — they may not match a
template and will fall back to the (optional) AI provider.

Run `animatica list-components` to list the registered components available to templates.

## Getting a free API key

Template prompts work offline with no key. For harder prompts, get a free key:

- Groq: https://console.groq.com (free tier)
- OpenRouter: https://openrouter.ai (free models, `:free`)
- NVIDIA NIM: https://build.nvidia.com (free tier)

Then run `animatica setup`, choose the provider, and paste the key (input is
hidden and stored mode 600).

## Editing storyboard.json

Every run saves `storyboard.json` next to the video. Open it in any text editor
to change titles, equations, or labels, then re-render with:

```
animatica make --from storyboard.json -o out/
```

No AI needed.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `animatica: command not found` | Activate your venv and `pip install -e .` |
| LaTeX not found | `animatica doctor --fix` or install TinyTeX (see Install) |
| ffmpeg not found | Install ffmpeg (see Install) |
| manim not importable | `pip install manim==0.22.1` |
| Video fails to render | Run `animatica doctor` and follow each FAIL fix |

Run `animatica doctor` to see the exact fix for each check on your machine.

## Glossary

- **Terminal**: the command-line app (PowerShell, Terminal, or bash).
- **Virtual environment**: an isolated folder for Python packages (`.venv`).
- **API key**: a secret token for a cloud AI provider (Groq, OpenRouter, NIM).
- **LaTeX**: the typesetting system used to render math equations.
- **Encoder**: turns rendered frames into an MP4 video (x264 by default).
- **Storyboard**: the `storyboard.json` file that describes a video scene by scene.


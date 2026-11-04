# Animatica setup — environment & procedure

Goal: **first full-quality video in ~25–40s** on any machine (real LaTeX, real ffmpeg),
with graceful fallbacks so setup never hard-fails.

## The one-liner

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/Abu103/animatica/main/scripts/bootstrap.sh | bash
# Windows (PowerShell)
irm https://raw.githubusercontent.com/Abu103/animatica/main/scripts/bootstrap.ps1 | iex
```

## What the bootstrap does (in order)

```
[0/3] uv            install uv if missing (curl astral.sh installer)     ~10s if needed
[1/3] python deps   uv venv .venv && uv pip install -e .                ~10-15s
      ── in parallel ──
[2/3] TinyTeX zip   download + unzip pre-baked tinytex-manim.zip         ~5-10s  (~85MB)
[3/3] verify        animatica doctor
```

Steps 1 and 2 run **concurrently**, so total wall time ≈ max(python, tex), not the sum.

## Components and why each is fast

| Component | Old way | Now | Quality |
|---|---|---|---|
| Python + manim | venv + pip (45–90s) | `uv venv` + `uv pip install` (10–15s) | 100% |
| ffmpeg | winget/brew/apt (30–60s) | `imageio-ffmpeg` wheel — a real static ffmpeg binary (~30MB, ~3s). `doctor` and the encoder probe auto-use it when no system ffmpeg exists | 100% |
| LaTeX | TinyTeX installer + `tlmgr install ...` (2–4 min, fragile) | pre-baked `tinytex-manim.zip` release asset, built once by CI | 100% |

## The TinyTeX artifact

`.github/workflows/build-tinytex.yml` runs on release (or manually), installs TinyTeX plus
exactly `standalone preview babel-english amsmath amsfonts dvisvgm` (the packages a fresh
TinyTeX lacks and Manim needs), zips `~/.TinyTeX`, and attaches it to the GitHub release.
Rebuild only when the package list changes — it almost never does.

## Environment variables

| Var | Purpose | Example |
|---|---|---|
| `ANIMATICA_GH_REPO` | Repo for `gh release download` (private-repo path) | `my-org/animatica` |
| `ANIMATICA_TINYTEX_URL` | Explicit (or pre-signed) URL of `tinytex-manim.zip` — tried first | `https://.../tinytex-manim.zip?token=...` |
| `GITHUB_TOKEN` | API fallback for private-repo asset download (CI/headless) | `ghp_...` |
| `ANIMATICA_CONFIG_DIR` | Override config dir (keys, config.toml) | `/tmp/animatica-cfg` |
| `ANIMATICA_MODEL` | Override the AI model id (same as `--model`) | `meta/llama-3.1-8b-instruct` |

## Private GitHub repos

Release assets of private repos require auth. The fetch order in both bootstrap scripts:

1. `ANIMATICA_TINYTEX_URL` (curl) — works for public repos or pre-signed URLs
2. `gh release download --repo $ANIMATICA_GH_REPO` — works if the user ran `gh auth login` once
3. `GITHUB_TOKEN` via the releases API — for CI/headless
4. **Fallback**: `animatica doctor --fix` (TinyTeX installer + tlmgr + ffmpeg) — slower but always works

## Post-install

```bash
source .venv/bin/activate            # Windows: .venv\Scripts\activate
# if the TinyTeX zip was used, add its bin dir to PATH for the session:
export PATH="$PWD/.tex/bin/<arch>:$PATH"     # Windows: $env:PATH = "$PWD\.tex\bin\windows;$env:PATH"
animatica doctor                     # verify; then:
animatica make "graph of sin(x)" -o out/     # first video, no key needed
animatica setup                      # optional: store a free AI key for any prompt
```

## Manual equivalent

```
pip install -e . && animatica doctor --fix && animatica doctor
```

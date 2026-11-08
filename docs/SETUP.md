# Animatica setup

Supported: **Linux** and **Windows** (Python 3.10+; CI tests Linux/3.13 and Windows/3.12).
Setup time depends on your connection; installing LaTeX is the slow part (minutes, not seconds).

## One-liner

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.sh | bash
```
```powershell
# Windows (PowerShell). Needs Git. Or run scripts\bootstrap.ps1 from a clone.
irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
```

Both scripts verify the installation with `animatica doctor`. When required checks
pass, an interactive terminal automatically launches `animatica setup` in the same
session. Choose `template` for offline starter examples, or choose a provider; a
cloud provider asks for permission and an API key. In CI or without an interactive
terminal, the wizard is skipped and the installer prints the command to run later.
Set `ANIMATICA_SKIP_SETUP=1` to skip it explicitly.

## What it does

1. Installs `uv` if missing, creates `.venv`, installs Animatica + Manim (re-running is safe).
2. If LaTeX is missing: runs `animatica doctor --fix --yes`.
   - **Windows:** the official upstream TinyTeX installer (`rstudio/tinytex`), then the TeX packages Manim needs.
     TinyTeX goes to `%APPDATA%\TinyTeX` (or `%ProgramData%\TinyTeX` if your user path has spaces/non-ASCII).
   - **Linux:** `apt install texlive texlive-latex-extra dvisvgm` (needs sudo).
3. Verifies with `animatica doctor`.
4. On an interactive terminal, launches `animatica setup` so you can choose an offline template or provider immediately. CI, redirected input, and `ANIMATICA_SKIP_SETUP=1` skip the prompt.

Animatica finds an installed TinyTeX by itself even if it is not on your PATH, so a restart is not required
for Animatica. (A program can never change its parent terminal's PATH; the TinyTeX installer adds it for *new* terminals.)

## Commands

```
animatica doctor              # check everything
animatica doctor --fix        # offer to install what is missing (--yes: no prompt)
python -m animatica doctor    # same, if the `animatica` script is not on PATH
animatica make "graph of sin(x)" -o out --preview
```

`ffmpeg`: a system ffmpeg is used if present, otherwise the binary bundled in the `imageio-ffmpeg` wheel.

## Pre-baked TinyTeX release asset

`.github/workflows/build-tinytex.yml` builds a **Linux** TinyTeX archive. It is a
Unix tree and must not be used on Windows.

`.github/workflows/build-tinytex-windows.yml` builds a separate **Windows**
TinyTeX archive (`tinytex-manim-win.zip`). `animatica doctor --fix` prefers it
on Windows, but only after verifying its sha256; when the hash is unknown or
does not match, the official installer above is used instead. See
`docs/NATIVE_DEPS.md` for the details.

## Known limits

- Windows support is verified by the `windows` CI job; see the CI badge/status rather than this document.
- Hindi/Devanagari text inside LaTeX equations can still fall back to plain text (pdfLaTeX limitation).

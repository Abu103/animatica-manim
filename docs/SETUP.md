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

## Sandbox fast path (agents, containers, CI)

For a machine that has only `curl`, `tar` and `sh` (no Python, no apt, no git needed):

```sh
curl -fsSL https://codeload.github.com/Abu103/animatica-manim/tar.gz/refs/heads/main | tar xz && sh animatica-manim-main/scripts/sandbox.sh
cd animatica-manim-main && . ./.animatica-env   # in every new shell
```

It runs `animatica doctor` and one smoke render, prints the time of each phase, and ends with
exactly one status line: `READY <seconds>s`, `DEGRADED <reason>` or `FAILED <reason>`. Exit status
is non-zero on `FAILED`, including a core install slower than `ANIMATICA_BUDGET_S` (default 60;
CI sets 120 for the codeload-only tier). LaTeX is fetched in the background and is not part of that
budget; `animatica doctor` reports it as still downloading until it lands.

Two layers. The **code layer** is the repo itself, always live: a `.pth` file points the runtime at
`src/`, so adding, changing or deleting code needs no rebuild. The **runtime layer** is a prebuilt,
relocatable directory (standalone CPython, every dependency from `pyproject.toml` including the test
and TUI extras, cairo/pango with the libraries they link against, and DejaVu fonts). The sandbox's
own Python, pip and apt are never used. Target: Linux x86_64 with glibc 2.36 or newer; anything
else goes straight to `scripts/bootstrap.sh`.

| Flag | Effect |
| --- | --- |
| `--no-tex` | do not fetch the TeX layer in the background |
| `--verify-only` | download nothing: run doctor and the smoke render on what is installed |
| `--runtime-only` | fetch the runtime only (no code layer, no verification, no TeX) |
| `--ref REF` | use another branch or tag; `ANIMATICA_REF` does the same (change the URL's ref too) |

Other variables: `ANIMATICA_BUDGET_S`, `ANIMATICA_GH_REPO`, `ANIMATICA_RELEASE_BASE`,
`ANIMATICA_CODELOAD_BASE`, `ANIMATICA_BOOTSTRAP`. Run `sh scripts/sandbox.sh --help` for the
short version. Re-running is safe: when the runtime key matches nothing is downloaded again, and
local edits to the checkout are never overwritten.

**Runtime key.** The first 12 hex characters of a sha256 over the dependency list (including the
optional extras), the Python minor version and the platform tag, from `scripts/runtime_key.sh`. The
script computes it from the checked-out `pyproject.toml`, so it is always the runtime that code needs.

**Fetch order and fallbacks.** Each step has its own timeout and every download is checked against
a checksum (a mismatch is a failed step, not a warning); failure moves to the next step:

1. Release asset `runtime-<key>` (fastest; needs `github.com`).
2. Branch `runtime-<key>` through `codeload.github.com`, in parts under 95 MB, joined and verified.
   This is the only host the most restricted networks reach.
3. Key not published yet: the newest runtime named in the `runtime-latest` branch. When PyPI answers,
   only the differing packages are installed; otherwise a `WARN` line lists the mismatch and the
   result is `DEGRADED`.
4. Nothing reachable: `scripts/bootstrap.sh`, unchanged.

**Keeping it fresh.** `.github/workflows/sandbox-runtime.yml` builds and publishes the runtime when
`pyproject.toml` or the build scripts change, and nightly repairs anything that went missing. It keeps
the last three `runtime-*` branches (force-pushed; nothing else may live there). In `ci.yml`,
`sandbox-runtime-gate` fails a change whose key has no published runtime, and `sandbox-fast-path`
runs the command above in a bare `debian:bookworm-slim` container on both network tiers and fails
over budget.

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

## Worker count

CI chooses how many workers the suite and the render gate use automatically:
cores versus memory (one test worker needs about 1.5 GB), raised to a minimum of
four and capped at twelve. Override either with `ANIMATICA_TEST_JOBS=N` (suite)
or `ANIMATICA_RENDER_JOBS=N` (gate); an invalid value is ignored with a printed
warning. `ci_tests.py` prints the chosen count first:

```
workers: 5 (cpus=8, mem=7.7GB, limit=mem)
```

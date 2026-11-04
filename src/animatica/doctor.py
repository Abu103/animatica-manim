"""Pre-flight dependency checks: `animatica doctor`."""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from animatica.config import load_config, load_key


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    fix: str


FREE_PROVIDER_TIP = (
    "for any prompt run 'animatica setup'. Free options: OpenRouter (:free models) openrouter.ai/keys, "
    "Groq console.groq.com/keys, NVIDIA build.nvidia.com, or local Ollama (no key, ollama.com)"
)


def _py_fix() -> str:
    return "install Python 3.10 or newer (python.org, or py -3.11 on Windows)"


def _manim_fix() -> str:
    return "pip install manim==0.22.1"


def _latex_fix() -> str:
    if sys.platform == "win32":
        return "install TinyTeX from https://yihui.org/tinytex/ (then restart your terminal)"
    return "install TinyTeX from https://yihui.org/tinytex/ (or `sudo apt install texlive texlive-latex-extra`)"


def _ffmpeg_fix() -> str:
    if sys.platform == "win32":
        return "install ffmpeg (`winget install ffmpeg`)"
    return "install ffmpeg (`brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Linux)"


def run_checks(run=subprocess.run, which=shutil.which, deep_latex: bool = True) -> list[CheckResult]:
    """Run every dependency check and return a CheckResult per check."""
    checks: list[CheckResult] = []

    # Python version
    py_ok = sys.version_info >= (3, 10)
    checks.append(
        CheckResult(
            "python",
            py_ok,
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "" if py_ok else _py_fix(),
        )
    )

    # Manim importable
    try:
        import manim

        manim_ok = True
        manim_detail = f"manim {getattr(manim, '__version__', '?')}"
    except Exception:  # pragma: no cover - environment
        manim_ok = False
        manim_detail = "manim not importable"
    checks.append(
        CheckResult("manim", manim_ok, manim_detail, "" if manim_ok else _manim_fix())
    )

    # LaTeX (latex + dvisvgm)
    latex_bin = which("latex")
    dvisvgm_bin = which("dvisvgm")
    latex_ok = bool(latex_bin) and bool(dvisvgm_bin)
    checks.append(
        CheckResult(
            "latex",
            latex_ok,
            f"latex={'yes' if latex_bin else 'no'} dvisvgm={'yes' if dvisvgm_bin else 'no'}",
            "" if latex_ok else _latex_fix(),
        )
    )

    # LaTeX packages: `latex` on PATH is not enough (TinyTeX ships without standalone/babel-english).
    if latex_ok and deep_latex:
        from animatica.latex_check import fix_for, probe_latex

        ok, reason, packages = probe_latex()
        checks.append(CheckResult("latex-packages", ok, reason, "" if ok else fix_for(packages)))

    # ffmpeg (system binary, or the real static binary bundled in the imageio-ffmpeg wheel)
    ffmpeg_bin = which("ffmpeg")
    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg

            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = None
    ffmpeg_detail = str(ffmpeg_bin) if ffmpeg_bin else "not found"
    if ffmpeg_bin and "imageio" in str(ffmpeg_bin):
        ffmpeg_detail += " (imageio-ffmpeg bundled binary)"
    checks.append(
        CheckResult(
            "ffmpeg",
            bool(ffmpeg_bin),
            ffmpeg_detail,
            "" if ffmpeg_bin else _ffmpeg_fix(),
        )
    )

    # Cairo/Pango via manim (only meaningful if manim present)
    cairo_ok = False
    cairo_detail = "manim absent"
    if manim_ok:
        try:
            import manim  # noqa: F401

            cairo_ok = True
            cairo_detail = "cairo/pango available via manim"
        except Exception:
            cairo_detail = "cairo/pango not available via manim"
    checks.append(CheckResult("cairo", cairo_ok, cairo_detail, "" if cairo_ok else _manim_fix()))

    # Encoders (ffmpeg present implies x264)
    enc_ok = bool(ffmpeg_bin)
    checks.append(
        CheckResult(
            "encoders",
            enc_ok,
            "x264 available via ffmpeg" if enc_ok else "no ffmpeg",
            "" if enc_ok else _ffmpeg_fix(),
        )
    )

    # Configured provider + key
    cfg = load_config()
    provider = cfg.provider
    if provider == "auto":
        prov_ok = True
        prov_detail = "no AI provider set: only a few canned example prompts work (offline)"
        prov_fix = FREE_PROVIDER_TIP
    else:
        key = load_key(provider)
        prov_ok = bool(key)
        prov_detail = f"provider {provider}, key {'set' if key else 'missing'}"
        prov_fix = "" if prov_ok else f"run 'animatica setup' to store a {provider} key"

    # cloud providers need cloud_allowed
    cloud = provider in ("groq", "openrouter", "nim")
    if cloud and not cfg.cloud_allowed:
        prov_ok = False
        prov_detail += "; cloud disabled"
        prov_fix = "run 'animatica setup' to allow cloud access"

    checks.append(CheckResult("provider", prov_ok, prov_detail, prov_fix))

    return checks



# Packages a fresh TinyTeX lacks but Animatica needs (the 2026-11-04 sessions hit exactly these).
TEX_PACKAGES = ("standalone", "preview", "babel-english", "amsmath", "amsfonts", "dvisvgm")


def fix_dependencies(run=subprocess.run, which=shutil.which, platform: str = sys.platform) -> list[str]:
    """Actually install missing deps (doctor --fix). Returns human-readable actions taken.

    Never aborts on one failure: every step is attempted and reported.
    """
    actions: list[str] = []

    def _try(label: str, cmd: list[str]) -> bool:
        try:
            result = run(cmd, capture_output=True, text=True)
            ok = getattr(result, "returncode", 0) == 0
        except Exception as exc:
            ok = False
            actions.append(f"failed: {label} ({exc})")
            return False
        if ok:
            actions.append(f"done: {label}")
        else:
            actions.append(f"failed: {label} (exit {getattr(result, 'returncode', '?')})")
        return ok

    # ffmpeg
    if not which("ffmpeg"):
        if platform == "win32":
            _try("install ffmpeg via winget", ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements"])
        elif platform == "darwin":
            _try("install ffmpeg via brew", ["brew", "install", "ffmpeg"])
        else:
            _try("install ffmpeg via apt", ["sudo", "apt", "install", "-y", "ffmpeg"])
        actions.append("restart your terminal so the new PATH applies" if which("ffmpeg") else "ffmpeg still not on PATH after install -- restart your terminal and re-run 'animatica doctor'")

    # LaTeX / TinyTeX
    latex_missing = not (which("latex") and which("dvisvgm"))
    if latex_missing:
        if platform == "win32":
            _try(
                "install TinyTeX",
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 "irm https://yihui.org/tinytex/install-windows.ps1 | iex"],
            )
        elif platform == "darwin":
            _try("install TinyTeX", ["bash", "-c", "curl -fsSL https://yihui.org/tinytex/install-unx.sh | sh"])
        else:
            _try("install TeX Live", ["sudo", "apt", "install", "-y", "texlive", "texlive-latex-extra"])
        actions.append("add the TinyTeX bin dir to PATH (Windows: C:\\tools\\tinytex\\bin\\windows) and restart your terminal")

    # TinyTeX packages (only when we just installed TeX and tlmgr is now on PATH)
    if latex_missing and which("tlmgr"):
        _try("install required TeX packages", ["tlmgr", "install", *TEX_PACKAGES])
    elif latex_missing:
        actions.append("tlmgr not found; if you installed TinyTeX, restart your terminal, then run: tlmgr install " + " ".join(TEX_PACKAGES))

    return actions

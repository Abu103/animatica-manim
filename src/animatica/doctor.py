"""Pre-flight dependency checks: `animatica doctor`."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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
        return "run `animatica doctor --fix` (installs TinyTeX), or see https://yihui.org/tinytex/ ; then open a new terminal"
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



# Official upstream Windows installer (verified to exist in rstudio/tinytex; the old
# yihui.org/tinytex/install-windows.ps1 URL returns 404).
TINYTEX_WIN_INSTALLER_URL = "https://raw.githubusercontent.com/rstudio/tinytex/main/tools/install-bin-windows.ps1"


def tinytex_bin_dirs(platform: str = sys.platform, env=None) -> list[Path]:
    """Places a TinyTeX `bin` directory may live, most likely first.

    Windows: the upstream installer uses %TINYTEX_DIR%, else %APPDATA% (only when it is plain
    ASCII), else %ProgramData%; Chocolatey uses C:\\tools\\tinytex.
    """
    env = os.environ if env is None else env
    dirs: list[Path] = []
    if platform == "win32":
        for base in (env.get("TINYTEX_DIR"), env.get("APPDATA"), env.get("ProgramData")):
            if base:
                dirs.append(Path(base) / "TinyTeX" / "bin" / "windows")
        dirs.append(Path("C:/tools/tinytex/bin/windows"))
    else:
        home = Path(env.get("HOME") or Path.home())
        for root in (home / ".TinyTeX" / "bin", home / "Library" / "TinyTeX" / "bin"):
            if root.is_dir():
                dirs.extend(sorted(p for p in root.iterdir() if p.is_dir()))
    return dirs


def ensure_tex_on_path(platform: str = sys.platform, env=None, is_ok=None) -> Path | None:
    """If latex/dvisvgm are not on PATH but a TinyTeX install exists, put it on THIS process's PATH.

    A fresh TinyTeX has `latex` and `tlmgr` but NOT `dvisvgm` (tlmgr installs that afterwards), so a
    bin dir counts as found when it has `latex`; requiring dvisvgm too would hide tlmgr and make the
    package install impossible.

    A child process can never change its parent shell's PATH, so Animatica makes TeX visible to
    itself (and to the Manim/LaTeX subprocesses it spawns) instead of relying on a restarted terminal.
    Returns the bin dir that was added, or None.
    """
    env = os.environ if env is None else env
    exe = ".exe" if platform == "win32" else ""
    if is_ok is None:
        def is_ok(d: Path) -> bool:
            return (d / f"latex{exe}").is_file()
    if shutil.which("latex", path=env.get("PATH")) and shutil.which("dvisvgm", path=env.get("PATH")):
        return None
    for d in tinytex_bin_dirs(platform, env):
        if is_ok(d):
            env["PATH"] = str(d) + os.pathsep + env.get("PATH", "")
            return d
    return None


def describe_tex_search(platform: str = sys.platform, env=None) -> str:
    """Human-readable list of where we looked for TinyTeX (for failure messages / CI logs)."""
    lines = [f"  {'FOUND  ' if d.is_dir() else 'missing'} {d}" for d in tinytex_bin_dirs(platform, env)]
    return "searched for TinyTeX in:\n" + ("\n".join(lines) if lines else "  (no candidate folders)")


def _bundled_ffmpeg():
    """Path of the static ffmpeg shipped in the imageio-ffmpeg wheel, or None."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


# Packages a fresh TinyTeX lacks but Animatica needs (the 2026-11-04 sessions hit exactly these).
TEX_PACKAGES = ("standalone", "preview", "babel-english", "amsmath", "amsfonts", "dvisvgm")


def fix_dependencies(run=subprocess.run, which=shutil.which, platform: str = sys.platform, bundled_ffmpeg=_bundled_ffmpeg) -> list[str]:
    """Actually install missing deps (doctor --fix). Returns human-readable actions taken.

    Never aborts on one failure: every step is attempted and reported.
    """
    actions: list[str] = []
    last_tail: list[str] = [""]  # last lines of the most recent command's output, for failure reports

    def _try(label: str, cmd: list[str]) -> bool:
        try:
            result = run(cmd, capture_output=True, text=True)
            ok = getattr(result, "returncode", 0) == 0
            out = f"{getattr(result, 'stdout', '') or ''}\n{getattr(result, 'stderr', '') or ''}"
            last_tail[0] = "\n".join("    | " + ln for ln in str(out).strip().splitlines()[-15:])
        except Exception as exc:
            ok = False
            actions.append(f"failed: {label} ({exc})")
            return False
        if ok:
            actions.append(f"done: {label}")
        else:
            actions.append(f"failed: {label} (exit {getattr(result, 'returncode', '?')})" + (f"\n{last_tail[0]}" if last_tail[0].strip() else ""))
        return ok

    # ffmpeg: the bundled imageio-ffmpeg binary is enough, so only install a system one if neither exists
    if not which("ffmpeg") and not bundled_ffmpeg():
        if platform == "win32":
            _try("install ffmpeg via winget", ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements"])
        elif platform == "darwin":
            _try("install ffmpeg via brew", ["brew", "install", "ffmpeg"])
        else:
            _try("install ffmpeg via apt", ["sudo", "apt", "install", "-y", "ffmpeg"])
        actions.append("restart your terminal so the new PATH applies" if which("ffmpeg") else "ffmpeg still not on PATH after install -- restart your terminal and re-run 'animatica doctor'")

    # LaTeX / TinyTeX
    ensure_tex_on_path(platform)  # already installed but not on PATH? just use it
    have_latex = bool(which("latex"))
    latex_missing = not (have_latex and which("dvisvgm"))
    if not have_latex:
        if platform == "win32":
            _try(
                "install TinyTeX (official rstudio/tinytex Windows installer)",
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 f"$ProgressPreference='SilentlyContinue'; irm {TINYTEX_WIN_INSTALLER_URL} | iex"],
            )
            added = ensure_tex_on_path(platform)
            if added:
                actions.append(f"TinyTeX found at {added}; added to PATH for Animatica (new terminals get it via 'tlmgr path add')")
            else:
                actions.append("TinyTeX installer ran but latex.exe was not found.\n" + describe_tex_search(platform)
                               + (f"\ninstaller output (last lines):\n{last_tail[0]}" if last_tail[0].strip() else ""))
        elif platform == "darwin":
            _try("install TinyTeX", ["bash", "-c", "curl -fsSL https://yihui.org/tinytex/install-unx.sh | sh"])
            ensure_tex_on_path(platform)
        else:
            _try("install TeX Live", ["sudo", "apt", "install", "-y", "texlive", "texlive-latex-extra", "dvisvgm"])

    # TinyTeX needs extra packages (dvisvgm, standalone, ...) via tlmgr; on Linux apt provides them.
    if latex_missing and platform != "linux":
        tlmgr = which("tlmgr")
        if tlmgr:
            _try("install required TeX packages", [tlmgr, "install", *TEX_PACKAGES])
        else:
            actions.append("tlmgr not found; open a new terminal, then run: tlmgr install " + " ".join(TEX_PACKAGES))

    return actions

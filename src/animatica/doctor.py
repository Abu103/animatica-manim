"""Pre-flight dependency checks: `animatica doctor`."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
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

#: Providers that do not require an API key: template (offline canned prompts)
#: and ollama (local LLM). The doctor check must not flag them as "key missing".
KEYLESS_PROVIDERS = frozenset({"template", "ollama"})


def _py_fix() -> str:
    return "install Python 3.10 or newer (python.org, or py -3.11 on Windows)"


def _manim_fix() -> str:
    return "pip install manim==0.22.1"


def _latex_fix() -> str:
    if sys.platform == "win32":
        return "run `animatica doctor --fix` (installs TinyTeX), or see https://yihui.org/tinytex/ ; then open a new terminal"
    return "install TinyTeX from https://yihui.org/tinytex/ (or `sudo apt install texlive texlive-latex-extra`)"


def _dvisvgm_fix() -> str:
    if sys.platform == "linux":
        return "latex is installed but dvisvgm is not: `sudo apt install dvisvgm` (or run `animatica doctor --fix`)"
    return "latex is installed but dvisvgm is not: run `tlmgr install dvisvgm` (or `animatica doctor --fix`)"


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
            "" if latex_ok else (_dvisvgm_fix() if latex_bin else _latex_fix()),
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
    elif provider in KEYLESS_PROVIDERS:
        prov_ok = True
        prov_detail = f"provider {provider} (no key needed)"
        prov_fix = ""
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
TINYTEX_WIN_INSTALL_ATTEMPTS = 3
TINYTEX_WIN_INSTALL_TIMEOUT_SECONDS = 600
TINYTEX_WIN_RETRY_BASE_SECONDS = 5


def project_roots() -> list[Path]:
    """Where a project-local TeX bundle may be: the checkout, then the CWD."""
    here = Path(__file__).resolve()
    candidates = []
    try:
        candidates.append(here.parents[2])
    except IndexError:  # pragma: no cover - installed layout without a checkout
        pass
    try:
        candidates.append(Path.cwd())
    except OSError:  # pragma: no cover
        pass
    seen: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.append(path)
    return seen


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
        # The prebuilt Windows bundle unpacks to <project>/.tex/bin/windows.
        from animatica.tex_bundle import bundle_bin_dirs

        dirs.extend(bundle_bin_dirs(Path.cwd()))
    else:
        home = Path(env.get("HOME") or Path.home())
        # An explicit override, then a TeX unpacked next to the project (that is
        # where the one-line installer puts the prebuilt bundle), then the user's
        # own TinyTeX.
        roots: list[Path] = []
        explicit = env.get("ANIMATICA_TEX_DIR")
        if explicit:
            roots.append(Path(explicit) / "bin")
        for base in project_roots():
            roots.append(base / ".tex" / "bin")
        roots.extend([home / ".TinyTeX" / "bin", home / "Library" / "TinyTeX" / "bin"])
        for root in roots:
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


def _locate_dvisvgm(tlmgr: str, exe: str, actions: list[str]) -> bool:
    """dvisvgm was installed but is not on PATH: look through the TinyTeX tree and use its folder."""
    bindir = Path(tlmgr).parent
    try:
        root = bindir.parents[1]  # <TinyTeX>/bin/<arch> -> <TinyTeX>
        hits = [h for h in root.rglob(f"dvisvgm{exe}") if h.is_file()]
    except (OSError, IndexError):
        return False
    if not hits:
        return False
    d = hits[0].parent
    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
    actions.append(f"dvisvgm found at {d}; added to PATH for Animatica")
    return True


# tlmgr can print one of these and still exit 0 (seen on a fresh Windows TinyTeX: "tlmgr itself needs
# to be updated ... Terminating"), which makes every `tlmgr install` a silent no-op.
TLMGR_ERROR_MARKERS = ("tlmgr itself needs to be updated", "Terminating; please see warning", "tlmgr: error")


# Packages a fresh TinyTeX lacks but Animatica needs (the 2026-11-04 sessions hit exactly these).
TEX_PACKAGES = ("standalone", "preview", "babel-english", "amsmath", "amsfonts", "dvisvgm", "xkeyval")

# Files Manim's default template needs -> the package that provides them. Checked with kpsewhich after
# installing, because tlmgr's exit code and messages are not reliable (it can "succeed" and install nothing).
NEEDED_TEX_FILES = {
    "standalone.cls": "standalone",
    "preview.sty": "preview",
    "xkeyval.sty": "xkeyval",
    "english.ldf": "babel-english",
    "amsmath.sty": "amsmath",
    "amssymb.sty": "amsfonts",
}


def _tex_tools(tlmgr: str, run, which, exe: str):
    """Return (have(file) -> bool, tl(*args) -> str) bound to this TeX install, or (None, None) without kpsewhich."""
    kpse = which("kpsewhich")
    if not kpse:
        cand = Path(tlmgr).parent / f"kpsewhich{exe}"
        kpse = str(cand) if cand.is_file() else None
    if not kpse:
        return None, None

    def have(name: str) -> bool:
        try:
            r = run([kpse, name], capture_output=True, text=True)
            return getattr(r, "returncode", 1) == 0 and bool((getattr(r, "stdout", "") or "").strip())
        except Exception:
            return False

    def tl(*args: str) -> str:
        try:
            r = run([tlmgr, *args], capture_output=True, text=True)
            return f"{getattr(r, 'stdout', '') or ''}\n{getattr(r, 'stderr', '') or ''}"
        except Exception as exc:
            return f"(tlmgr failed: {exc})"

    return have, tl


def _missing_tex_files(tlmgr: str, run, which, exe: str) -> list[str] | None:
    """Needed TeX files kpsewhich cannot find; None when that cannot be checked (no kpsewhich)."""
    have, _ = _tex_tools(tlmgr, run, which, exe)
    if have is None:
        return None
    return [f for f in NEEDED_TEX_FILES if not have(f)]


def _ensure_tex_files(tlmgr: str, run, which, exe: str, actions: list[str]) -> None:
    """Verify each needed TeX file exists; install the owning package (found via tlmgr search) if not."""
    have, tl = _tex_tools(tlmgr, run, which, exe)
    if have is None:
        return

    for fname, pkg in NEEDED_TEX_FILES.items():
        if have(fname):
            continue
        out = tl("install", pkg)
        if not have(fname):
            # the guessed package name may be wrong for this TeX Live: ask tlmgr who owns the file
            found = re.findall(r"^([A-Za-z0-9_.+-]+):\s*$", tl("search", "--file", "--global", f"/{fname}"), re.M)
            for owner in dict.fromkeys(found):
                if owner != pkg:
                    out += "\n" + tl("install", owner)
                if have(fname):
                    break
        if have(fname):
            actions.append(f"done: TeX file {fname} is now available (package {pkg})")
        else:
            tail = "\n".join("    | " + ln for ln in out.strip().splitlines()[-8:])
            actions.append(f"failed: TeX file {fname} still missing after installing {pkg}\n{tail}")



def fix_dependencies(
    run=subprocess.run,
    which=shutil.which,
    platform: str = sys.platform,
    bundled_ffmpeg=_bundled_ffmpeg,
    sleep=time.sleep,
) -> list[str]:
    """Actually install missing deps (doctor --fix). Returns human-readable actions taken.

    Never aborts on one failure: every step is attempted and reported.
    """
    actions: list[str] = []
    last_tail: list[str] = [""]  # last lines of the most recent command's output, for failure reports

    def _try(
        label: str,
        cmd: list[str],
        show_output: bool = False,
        fail_on: tuple[str, ...] = (),
        timeout: float | None = None,
    ) -> bool:
        kwargs = {"capture_output": True, "text": True}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            result = run(cmd, **kwargs)
            ok = getattr(result, "returncode", 0) == 0
            out = f"{getattr(result, 'stdout', '') or ''}\n{getattr(result, 'stderr', '') or ''}"
            last_tail[0] = "\n".join("    | " + ln for ln in str(out).strip().splitlines()[-15:])
            if ok and any(m in str(out) for m in fail_on):
                ok = False  # e.g. tlmgr prints "Terminating" but exits 0
                result = type("R", (), {"returncode": "0, but its output reports an error"})()
        except Exception as exc:
            captured = [getattr(exc, "stdout", None) or getattr(exc, "output", None), getattr(exc, "stderr", None)]
            lines: list[str] = []
            for value in captured:
                if isinstance(value, bytes):
                    value = value.decode(errors="replace")
                if value:
                    lines.extend(str(value).strip().splitlines())
            last_tail[0] = "\n".join("    | " + ln for ln in lines[-15:])
            details = f"\n{last_tail[0]}" if last_tail[0] else ""
            actions.append(f"failed: {label} ({exc}){details}")
            return False
        if ok:
            actions.append(f"done: {label}" + (f"\n{last_tail[0]}" if show_output and last_tail[0].strip() else ""))
        else:
            actions.append(f"failed: {label} (exit {getattr(result, 'returncode', '?')})" + (f"\n{last_tail[0]}" if last_tail[0].strip() else ""))
        return ok

    def _apt(*pkgs: str) -> list[str]:
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        return ([] if is_root or not which("sudo") else ["sudo"]) + ["apt", "install", "-y", *pkgs]

    # ffmpeg: the bundled imageio-ffmpeg binary is enough, so only install a system one if neither exists
    if not which("ffmpeg") and not bundled_ffmpeg():
        if platform == "win32":
            _try("install ffmpeg via winget", ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements"])
        elif platform == "darwin":
            _try("install ffmpeg via brew", ["brew", "install", "ffmpeg"])
        else:
            _try("install ffmpeg via apt", _apt("ffmpeg"))
        actions.append("restart your terminal so the new PATH applies" if which("ffmpeg") else "ffmpeg still not on PATH after install -- restart your terminal and re-run 'animatica doctor'")

    # LaTeX / TinyTeX
    ensure_tex_on_path(platform)  # already installed but not on PATH? just use it
    have_latex = bool(which("latex"))
    latex_missing = not (have_latex and which("dvisvgm"))
    if not have_latex:
        if platform == "win32":
            # 1) the prebuilt Windows bundle (verified against a pinned sha256).
            #    It fails closed when no hash is known, and falls through on any
            #    download/checksum/unpack error.
            try:
                from animatica import tex_bundle

                bundle_ok, bundle_msg = tex_bundle.install_windows_bundle(Path.cwd())
            except Exception as exc:  # a bundle problem must never block the fallback
                bundle_ok, bundle_msg = False, f"prebuilt bundle unavailable: {type(exc).__name__}: {exc}"
            actions.append(bundle_msg)
            if bundle_ok:
                ensure_tex_on_path(platform)
                if which("latex"):
                    have_latex = True
                    latex_missing = not bool(which("dvisvgm"))
                    actions.append("prebuilt TinyTeX bundle is in use; no upstream install needed")
            if not have_latex:
                # 2) the official upstream installer (the fallback).
                # The published tinytex-manim.zip is built from install-unx.sh on Ubuntu;
                # it is not a Windows fallback. Retry the official Windows installer instead.
                installer = [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                    f"$ProgressPreference='SilentlyContinue'; irm {TINYTEX_WIN_INSTALLER_URL} | iex",
                ]
                tinytex_ready = False
                for attempt in range(1, TINYTEX_WIN_INSTALL_ATTEMPTS + 1):
                    _try(
                        f"install TinyTeX via the official Windows installer (attempt {attempt}/{TINYTEX_WIN_INSTALL_ATTEMPTS})",
                        installer,
                        timeout=TINYTEX_WIN_INSTALL_TIMEOUT_SECONDS,
                    )
                    added = ensure_tex_on_path(platform)
                    if which("latex"):
                        if added:
                            actions.append(f"TinyTeX found at {added}; added to PATH for Animatica (new terminals get it via 'tlmgr path add')")
                        else:
                            actions.append(f"TinyTeX latex.exe is available after attempt {attempt}/{TINYTEX_WIN_INSTALL_ATTEMPTS}")
                        tinytex_ready = True
                        have_latex = True
                        break
                    if attempt < TINYTEX_WIN_INSTALL_ATTEMPTS:
                        delay = TINYTEX_WIN_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                        actions.append(
                            f"latex.exe was not found after TinyTeX attempt {attempt}/{TINYTEX_WIN_INSTALL_ATTEMPTS}; "
                            f"retrying in {delay}s"
                        )
                        sleep(delay)
                if not tinytex_ready:
                    actions.append(
                        f"TinyTeX install failed after {TINYTEX_WIN_INSTALL_ATTEMPTS} attempts; latex.exe was not found.\n"
                        + describe_tex_search(platform)
                        + (f"\ninstaller output (last lines):\n{last_tail[0]}" if last_tail[0].strip() else "")
                    )
        elif platform == "darwin":
            _try("install TinyTeX", ["bash", "-c", "curl -fsSL https://yihui.org/tinytex/install-unx.sh | sh"])
            ensure_tex_on_path(platform)
        else:
            _try("install TeX Live", _apt("texlive", "texlive-latex-extra", "dvisvgm"))
    elif latex_missing and platform == "linux":
        # latex exists but dvisvgm does not (e.g. a bare texlive-base): apt can add just that
        _try("install dvisvgm via apt", _apt("dvisvgm"))

    # TinyTeX needs extra packages (dvisvgm, standalone, ...) via tlmgr. On Linux apt provides them.
    # Repair when TeX was just installed/incomplete, OR when TeX is present but kpsewhich shows a file Manim
    # needs is missing (seen on Windows: latex+dvisvgm present, babel-english missing, `doctor --fix` did
    # nothing). A healthy install is left alone: no tlmgr self-update, no network, no surprises.
    tlmgr = which("tlmgr") if platform != "linux" else None
    needs_repair = latex_missing
    if tlmgr and not latex_missing:
        missing = _missing_tex_files(tlmgr, run, which, ".exe" if platform == "win32" else "")
        needs_repair = bool(missing)
        if missing:
            actions.append("TeX is installed but these files are missing: " + ", ".join(missing))
    if needs_repair and platform != "linux":
        if tlmgr:
            exe = ".exe" if platform == "win32" else ""
            # dvisvgm first and on its own: Manim cannot work without it, and one bad package name
            # elsewhere must not hide whether it installed. tlmgr output is shown even on success,
            # because tlmgr can print an error and still exit 0.
            # A fresh TinyTeX is older than its package repository, and tlmgr then refuses to install
            # anything until it has updated itself. Do that first.
            _try("update tlmgr itself", [tlmgr, "update", "--self"], show_output=True)
            _try("install dvisvgm", [tlmgr, "install", "dvisvgm"], show_output=True, fail_on=TLMGR_ERROR_MARKERS)
            _try("install required TeX packages", [tlmgr, "install", *TEX_PACKAGES], show_output=True, fail_on=TLMGR_ERROR_MARKERS)
            _ensure_tex_files(tlmgr, run, which, exe, actions)
            if not which("dvisvgm"):
                _locate_dvisvgm(tlmgr, exe, actions)
            if not which("dvisvgm"):
                _try("reinstall dvisvgm", [tlmgr, "install", "--reinstall", "dvisvgm"], show_output=True, fail_on=TLMGR_ERROR_MARKERS)
                _locate_dvisvgm(tlmgr, exe, actions)
            if not which("dvisvgm"):
                bindir = Path(tlmgr).parent
                try:
                    near = sorted(p.name for p in bindir.glob("dvi*"))
                except OSError:
                    near = []
                actions.append("dvisvgm is still not found after tlmgr install. Diagnostics:")
                actions.append(f"  dvi* files in {bindir}: {near or 'none'}")
                _try("tlmgr info dvisvgm", [tlmgr, "info", "dvisvgm"], show_output=True)
                _try("tlmgr repository", [tlmgr, "option", "repository"], show_output=True)
        else:
            actions.append("tlmgr not found; open a new terminal, then run: tlmgr install " + " ".join(TEX_PACKAGES))

    return actions

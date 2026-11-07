"""Make the bundled cairo/pango libraries usable without any shell setup.

`pycairo` and `manimpango` are compiled against cairo and pango, which a stripped
container (no apt, no ``libcairo2``) does not have. ``scripts/bootstrap.sh`` can
drop a prebuilt copy of those libraries into ``native/lib``; this module makes
that directory work for the current process (by preloading the libraries with
``RTLD_GLOBAL``, which resolves the ``NEEDED`` entries of the extension modules)
and for child processes such as the ``manim`` render subprocess (by exporting
``LD_LIBRARY_PATH``).

Everything here is best-effort: a missing directory is not an error, and a
library that fails to load is simply retried later in the pass or ignored.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Environment override, handy for tests and for unusual installs.
NATIVE_DIR_ENV = "ANIMATICA_NATIVE_DIR"

_lib_dir: Path | None = None
_done = False


def candidate_dirs() -> list[Path]:
    """Directories that may hold ``libcairo.so.2`` … ``libpangocairo-1.0.so.0``."""
    out: list[Path] = []
    override = os.environ.get(NATIVE_DIR_ENV)
    if override:
        out.append(Path(override))
    here = Path(__file__).resolve()
    # src/animatica/_nativelibs.py -> repo root, and installed-package siblings
    out.append(here.parent.parent.parent / "native" / "lib")
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    out.append(data_home / "animatica" / "native" / "lib")
    return out


def find_lib_dir() -> Path | None:
    """First candidate that actually contains ``libcairo.so.2``."""
    for d in candidate_dirs():
        try:
            if d.is_dir() and any(d.glob("libcairo.so*")):
                return d
        except OSError:
            continue
    return None


def preload(lib_dir: Path) -> int:
    """``dlopen`` every library in *lib_dir* with ``RTLD_GLOBAL``.

    Libraries are loaded in dependency order by repeating passes: one that needs
    a library not yet loaded fails, and succeeds on a later pass. Returns the
    number of libraries loaded.
    """
    import ctypes

    try:
        pending = sorted(p for p in lib_dir.iterdir() if ".so" in p.name and p.is_file())
    except OSError:
        return 0
    loaded = 0
    for _ in range(len(pending) + 1):
        progress = False
        for path in list(pending):
            try:
                ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                continue
            pending.remove(path)
            loaded += 1
            progress = True
        if not progress:
            break
    return loaded


def ensure() -> Path | None:
    """Locate and activate the bundle once per process. Never raises."""
    global _lib_dir, _done
    if _done:
        return _lib_dir
    _done = True
    try:
        lib_dir = find_lib_dir()
        if lib_dir is None:
            return None
        preload(lib_dir)
        # Children (the `manim` subprocess, ffmpeg) inherit this.
        current = os.environ.get("LD_LIBRARY_PATH", "")
        parts = [p for p in current.split(os.pathsep) if p]
        if str(lib_dir) not in parts:
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join([str(lib_dir), *parts])
        _lib_dir = lib_dir
        return lib_dir
    except Exception:  # pragma: no cover - defensive: setup must never break startup
        return None


def activated() -> bool:
    """True when the current process is using a bundled library directory."""
    ensure()
    return _lib_dir is not None

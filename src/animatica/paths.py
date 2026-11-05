"""Path helpers for the LaTeX toolchain.

LaTeX reads the .tex file name as part of its first input line, so characters that are special to TeX
break it. The one that bites in practice is `~`: Windows hands out 8.3 short names such as
`C:\\Users\\RUNNER~1\\AppData\\Local\\Temp`, and `~` is an active character in LaTeX, so latex aborts with
"Emergency stop" before reading anything. Expanding to the long name removes the `~`.
"""
from __future__ import annotations

import sys
from pathlib import Path

TEX_UNSAFE_CHARS = "~%#{}^"


def _win_long_name(path: str) -> str | None:
    import ctypes

    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetLongPathNameW(path, buf, 32768)  # type: ignore[attr-defined]
    return buf.value if 0 < n < 32768 else None


def long_path(p, platform: str = sys.platform, expand=_win_long_name) -> Path:
    """Expand Windows 8.3 short names (RUNNER~1 -> runneradmin). No-op elsewhere. Never raises.

    The path may not exist yet: the nearest existing parent is expanded and the rest appended.
    """
    path = Path(p)
    if platform != "win32":
        return path
    try:
        path = path.absolute()
        tail: list[str] = []
        probe = path
        while not probe.exists() and probe.parent != probe:
            tail.insert(0, probe.name)
            probe = probe.parent
        full = expand(str(probe))
        return Path(full, *tail) if full else path
    except Exception:
        return path


def tex_unsafe_chars(p) -> str:
    """Characters in `p` that LaTeX cannot take in a file name (empty string when the path is fine)."""
    return "".join(sorted({c for c in str(p) if c in TEX_UNSAFE_CHARS}))


def check_tex_safe(p) -> None:
    bad = tex_unsafe_chars(p)
    if bad:
        raise RuntimeError(
            f"The output folder path contains {bad!r}, which LaTeX cannot handle in a file name: {p}\n"
            "Choose an output folder (-o) whose full path has none of these characters."
        )

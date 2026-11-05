"""End-to-end LaTeX probe: compile one tiny formula exactly the way Manim does."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from animatica.components._latex import _tail_reason, install_hint

_PROBE = (
    "import sys\n"
    "from manim import MathTex, config\n"
    "config.media_dir = sys.argv[1]\n"
    "config.verbosity = 'ERROR'\n"
    "MathTex(r'F_{n-1} + x^2')\n"
)


def log_excerpt(text: str, lines: int = 8) -> str:
    """The first TeX error with a little context, on one line (for doctor output / CI logs)."""
    rows = text.splitlines()
    for i, row in enumerate(rows):
        if row.startswith("!"):
            return " / ".join(r.strip() for r in rows[i : i + lines] if r.strip())[:600]
    return " / ".join(r.strip() for r in rows[-lines:] if r.strip())[:600]


def probe_latex(run=subprocess.run, timeout: int = 120) -> tuple[bool, str, list[str]]:
    """Return (ok, reason, missing_packages). Never raises."""
    with tempfile.TemporaryDirectory(prefix="animatica_tex_") as tmp:
        try:
            proc = run([sys.executable, "-c", _PROBE, tmp], capture_output=True, text=True, timeout=timeout)
        except Exception as exc:  # timeout, missing interpreter...
            return False, f"LaTeX probe could not run: {type(exc).__name__}", []
        if proc.returncode == 0:
            return True, "a test formula compiled", []
        logs = sorted(Path(tmp).rglob("*.log"), key=lambda p: p.stat().st_mtime)
        if logs:
            text = logs[-1].read_text(encoding="utf-8", errors="replace")
            reason, packages = _tail_reason(text)
            if not packages:
                reason = f"{reason} [log: {log_excerpt(text)}]"
            return False, reason, packages
        last = (proc.stderr or "").strip().splitlines()
        return False, (last[-1][:160] if last else "LaTeX test compile failed"), []


def fix_for(packages: list[str]) -> str:
    return (f"{install_hint(packages)}   (TinyTeX; with MiKTeX install the same packages in MiKTeX Console), "
            "then re-run `animatica doctor`")


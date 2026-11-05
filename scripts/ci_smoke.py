"""Real end-to-end smoke test, identical on Linux and Windows.

Renders actual videos through the CLI (offline template provider) into an output path containing a
space and a non-ASCII character, then checks each MP4 with PyAV (a Manim dependency; used here
instead of ffprobe, which is not guaranteed on Windows). Exit code 0 only if every render worked.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import av

PROMPTS = [
    "graph of sin(x)",
    "explain the pythagorean theorem a^2 + b^2 = c^2",
    "bar chart of sales by quarter",
]


def check_video(path: Path) -> str:
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"FAIL: missing/empty video {path}")
    with av.open(str(path)) as c:
        v = [s for s in c.streams if s.type == "video"]
        if not v:
            raise SystemExit(f"FAIL: no video stream in {path}")
        seconds = float(c.duration) / av.time_base if c.duration else 0.0
        if seconds < 1.0:
            raise SystemExit(f"FAIL: {path} is only {seconds:.2f}s long")
        return f"{v[0].codec_context.name} {v[0].width}x{v[0].height} {seconds:.1f}s"


def main() -> int:
    env = dict(os.environ, PYTHONUTF8="1")
    base = Path(tempfile.mkdtemp(prefix="animatica smoke ü "))
    failures = 0
    for i, prompt in enumerate(PROMPTS):
        out = base / f"out {i} é"
        cmd = [sys.executable, "-m", "animatica", "make", prompt, "-o", str(out), "--preview"]
        print(f"\n=== {prompt!r} -> {out}", flush=True)
        r = subprocess.run(cmd, env=env)
        if r.returncode != 0:
            print(f"FAIL: exit {r.returncode}")
            failures += 1
            continue
        try:
            print("OK:", check_video(out / "video.mp4"))
        except SystemExit as e:
            print(e)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

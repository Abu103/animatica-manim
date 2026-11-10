"""Conformance corpus: storyboards every backend must render identically."""
from __future__ import annotations

import json
from pathlib import Path

from animatica.backends.base import RenderBackend, RenderOptions
from animatica.storyboard.models import load_storyboard

CONFORMANCE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "conformance"

#: How far a rendered duration may drift from the promised one, in seconds.
DURATION_TOLERANCE = 0.2


def conformance_check(
    backend: RenderBackend,
    tmp: Path,
    conformance_dir: Path | None = None,
    jobs: int | None = None,
) -> list[str]:
    """Render every conformance storyboard and report failures.

    Each failure is a human-readable string; an empty list means full conformance.
    The storyboards are rendered at the same time: the corpus is small and
    every render is a subprocess, so the machine's cores are the limit.
    """
    from animatica.backends.scheduler import run_in_parallel

    cd = conformance_dir or CONFORMANCE_DIR
    expected = json.loads((cd / "expected.json").read_text(encoding="utf-8"))
    failures: list[str] = []

    def render_one(fname: str) -> tuple[str, dict, list[float]]:
        sb_path = cd / fname
        sb = load_storyboard(sb_path)
        out_dir = tmp / sb_path.stem
        result = backend.render(sb, out_dir, RenderOptions(quality="preview"))
        return fname, {"scenes": len(sb.scenes)}, list(result.durations)

    for fname, facts, durations in run_in_parallel(list(expected), render_one, workers=jobs):
        exp = expected[fname]
        exp_scenes = exp.get("scenes")
        if exp_scenes is not None and facts["scenes"] != exp_scenes:
            failures.append(
                f"{fname}: scene count {facts['scenes']} != expected {exp_scenes}"
            )
        exp_dur = exp.get("duration")
        if exp_dur is not None:
            actual_dur = sum(durations)
            if abs(actual_dur - exp_dur) > DURATION_TOLERANCE:
                failures.append(
                    f"{fname}: duration {actual_dur:.2f}s != expected {exp_dur}s"
                )
    return failures


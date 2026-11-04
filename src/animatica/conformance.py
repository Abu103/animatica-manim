"""Conformance corpus: storyboards every backend must render identically."""
from __future__ import annotations

import json
from pathlib import Path

from animatica.backends.base import RenderBackend, RenderOptions
from animatica.storyboard.models import load_storyboard

CONFORMANCE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "conformance"


def conformance_check(backend: RenderBackend, tmp: Path, conformance_dir: Path | None = None) -> list[str]:
    """Render every conformance storyboard and report failures.

    Each failure is a human-readable string; an empty list means full conformance.
    """
    cd = conformance_dir or CONFORMANCE_DIR
    expected = json.loads((cd / "expected.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    for fname, exp in expected.items():
        sb_path = cd / fname
        sb = load_storyboard(sb_path)
        out_dir = tmp / sb_path.stem
        result = backend.render(sb, out_dir, RenderOptions(quality="preview"))
        exp_scenes = exp.get("scenes")
        if exp_scenes is not None and len(sb.scenes) != exp_scenes:
            failures.append(
                f"{fname}: scene count {len(sb.scenes)} != expected {exp_scenes}"
            )
        exp_dur = exp.get("duration")
        if exp_dur is not None:
            actual_dur = sum(result.durations)
            if abs(actual_dur - exp_dur) > 0.2:
                failures.append(
                    f"{fname}: duration {actual_dur:.2f}s != expected {exp_dur}s"
                )
    return failures


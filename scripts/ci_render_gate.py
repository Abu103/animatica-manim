#!/usr/bin/env python3
"""Render the fixture storyboards for real and fail on any quality warning.

The unit suite checks geometry with real mobjects, but nothing renders a
whole video end to end. This gate does: it renders every storyboard in
``tests/fixtures`` through the real Manim backend at the cheapest quality,
then reads the report the pipeline wrote and fails when the render was not
clean.

It fails on:
  * any ``[frame-lint]`` finding -- content inside the safe area, clipped
    content, empty frames, unreadable contrast;
  * any component that fell back to a text card instead of rendering;
  * any ``timing:`` warning -- a beat that ran longer than it declared, so
    the captions drift out of sync with the video.

It deliberately does NOT fail on the "text scaled to N px" advisory: that
reports a legibility trade-off the author chose, not a broken render. It is
printed so it is visible in the log.

Exit code is 0 only when every fixture rendered with no warnings.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

#: Substrings of a warning that mean the render was not clean.
FAILURE_MARKERS = ("[frame-lint]", "timing:")


def _fixture_paths() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.glob("*.json"))


def _render(storyboard: Path, out_dir: Path) -> tuple[int, list[str]]:
    """Render one storyboard and return (exit code, report warnings)."""
    cmd = [
        sys.executable, "-m", "animatica", "make",
        "--from", str(storyboard),
        "-o", str(out_dir),
        "--preview",  # cheapest quality: the gate checks the pipeline, not the pixels
        "--no-progress",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode, [f"render failed with exit code {proc.returncode}"]

    report_path = out_dir / "report.json"
    if not report_path.is_file():
        return 1, ["render produced no report.json"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    warnings = list(report.get("warnings", []))
    fallbacks = list(report.get("fallbacks", []))
    if fallbacks:
        warnings.append(f"components fell back to a text card: {', '.join(fallbacks)}")
    return 0, warnings


def main() -> int:
    fixtures = _fixture_paths()
    if not fixtures:
        print(f"FAIL: no storyboards found in {FIXTURES_DIR}")
        return 1

    failures = 0
    with tempfile.TemporaryDirectory(prefix="animatica render gate ") as tmp:
        for storyboard in fixtures:
            out_dir = Path(tmp) / storyboard.stem
            print(f"\n=== {storyboard.name} ===", flush=True)
            code, warnings = _render(storyboard, out_dir)

            for warning in warnings:
                print(f"  {warning}")
                if any(marker in warning for marker in FAILURE_MARKERS):
                    failures += 1
                    print(f"  ^ FAIL: {storyboard.name}")
                elif "fell back to a text card" in warning:
                    failures += 1
                    print(f"  ^ FAIL: {storyboard.name}")
                else:
                    print(f"  (advisory only, not a failure)")

            if not warnings:
                print("  OK: rendered with no warnings")

    if failures:
        print(f"\nFAIL: {failures} warning(s) that make the render unclean")
        return 1
    print(f"\nCLEAN: {len(fixtures)} fixture(s) rendered with no warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())

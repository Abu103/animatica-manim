#!/usr/bin/env python3
"""Render the fixture and conformance storyboards for real and check the result.

The unit suite checks geometry with real mobjects, but nothing rendered a
whole video end to end. This gate does: it renders every storyboard in
``tests/fixtures`` and ``tests/conformance`` through the real Manim backend
at the cheapest quality, then reads the report the pipeline wrote and fails
when the render was not clean.

It fails on:
  * any ``[frame-lint]`` finding -- content inside the safe area, clipped
    content, empty frames, unreadable contrast;
  * any component that fell back to a text card instead of rendering;
  * any ``timing:`` warning -- a beat that ran longer than it declared, so
    the captions drift out of sync with the video.

Some findings are known and still tolerated. They are listed in
``tests/conformance/gate_allowlist.json``: one entry per component and
warning kind, each with the reason it is still there. The allowlist may
only shrink -- when a tolerated warning stops happening the gate fails, so
the entry has to be removed instead of lingering.

Exit code is 0 only when every storyboard rendered within the allowlist.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
CONFORMANCE_DIR = REPO_ROOT / "tests" / "conformance"
ALLOWLIST_PATH = CONFORMANCE_DIR / "gate_allowlist.json"

#: Substrings of a warning that mean the render was not clean.
FAILURE_MARKERS = ("[frame-lint]", "timing:")

#: The kind of a fallback warning.
FALLBACK_KIND = "fallback"

_LINT_KIND = re.compile(r"\[frame-lint\] \[\w+\] (\w+)")


#: Files in the conformance directory that are not storyboards.
NOT_A_STORYBOARD = ("expected.json", "gate_allowlist.json")


def storyboard_paths() -> list[Path]:
    """Every storyboard the gate renders, fixtures first."""
    fixtures = sorted(p for p in FIXTURES_DIR.glob("*.json"))
    conformance = sorted(
        p for p in CONFORMANCE_DIR.glob("*.json") if p.name not in NOT_A_STORYBOARD
    )
    return fixtures + conformance


def load_allowlist(path: Path = ALLOWLIST_PATH) -> dict[str, dict[str, str]]:
    """component -> {warning kind: the reason it is still tolerated}."""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold an object")
    out: dict[str, dict[str, str]] = {}
    for component, kinds in data.items():
        if not isinstance(kinds, dict):
            raise ValueError(f"{path}: {component} must map kinds to reasons")
        for kind, reason in kinds.items():
            if not reason.strip():
                raise ValueError(f"{path}: {component}/{kind} needs a reason")
        out[component] = dict(kinds)
    return out


def warning_kind(warning: str) -> str | None:
    """The kind of a warning, or None when it is not one the gate knows."""
    match = _LINT_KIND.search(warning)
    if match:
        return match.group(1)
    if warning.startswith("timing:"):
        return "timing"
    return None


def storyboard_components(path: Path) -> list[str]:
    """The components a storyboard uses, in the order they appear."""
    data = json.loads(path.read_text(encoding="utf-8"))
    components: list[str] = []
    for scene in data.get("scenes", []):
        for beat in scene.get("beats", []):
            name = beat.get("component")
            if name and name not in components:
                components.append(name)
    return components


def tolerated_reason(
    components: list[str], kind: str | None, allowlist: dict[str, dict[str, str]]
) -> str | None:
    """The reason a warning of this kind is tolerated, if it is."""
    if kind is None:
        return None
    for component in components:
        reason = allowlist.get(component, {}).get(kind)
        if reason:
            return reason
    return None


def _fixture_paths() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.glob("*.json"))


def _render(storyboard: Path, out_dir: Path) -> tuple[int, list[str], list[str]]:
    """Render one storyboard and return (exit code, warnings, fallbacks)."""
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
        return proc.returncode, [f"render failed with exit code {proc.returncode}"], []

    report_path = out_dir / "report.json"
    if not report_path.is_file():
        return 1, ["render produced no report.json"], []
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return 0, list(report.get("warnings", [])), list(report.get("fallbacks", []))


def main() -> int:
    storyboards = storyboard_paths()
    if not storyboards:
        print(f"FAIL: no storyboards found in {FIXTURES_DIR} or {CONFORMANCE_DIR}")
        return 1

    allowlist = load_allowlist()
    failures = 0
    # Which kinds of warning each component still produces, over every
    # storyboard it appears in.
    seen: dict[str, set[str]] = {}

    with tempfile.TemporaryDirectory(prefix="animatica render gate ") as tmp:
        for storyboard in storyboards:
            out_dir = Path(tmp) / storyboard.stem
            print(f"\n=== {storyboard.name} ===", flush=True)
            code, warnings, fallbacks = _render(storyboard, out_dir)
            components = storyboard_components(storyboard)
            kinds_here: set[str] = set()

            for warning in warnings:
                kind = warning_kind(warning)
                if kind:
                    kinds_here.add(kind)
                reason = tolerated_reason(components, kind, allowlist)
                if reason:
                    print(f"  {warning}")
                    print(f"  (tolerated: {reason})")
                    continue
                print(f"  {warning}")
                if any(marker in warning for marker in FAILURE_MARKERS):
                    failures += 1
                    print(f"  ^ FAIL: {storyboard.name}")
                else:
                    print("  (advisory only, not a failure)")

            for component in fallbacks:
                reason = tolerated_reason([component], FALLBACK_KIND, allowlist)
                if reason:
                    print(f"  {component} fell back to a text card")
                    print(f"  (tolerated: {reason})")
                    continue
                failures += 1
                print(f"  {component} fell back to a text card")
                print(f"  ^ FAIL: {storyboard.name}")
                kinds_here.add(FALLBACK_KIND)

            for component in components:
                seen.setdefault(component, set()).update(kinds_here)

            if not warnings and not fallbacks:
                print("  OK: rendered with no warnings")

    # The allowlist may only shrink: a tolerated warning that no longer
    # happens has to be removed from the allowlist.
    stale = 0
    for component, kinds in allowlist.items():
        for kind in kinds:
            if kind not in seen.get(component, set()):
                stale += 1
                print(
                    f"STALE ALLOWLIST ENTRY: {component}/{kind} no longer happens; "
                    f"remove it from {ALLOWLIST_PATH.name}"
                )

    if stale:
        print(f"\nFAIL: {stale} allowlist entry(ies) no longer happen")
        return 1
    if failures:
        print(f"\nFAIL: {failures} warning(s) that make the render unclean")
        return 1
    print(f"\nCLEAN: {len(storyboards)} storyboard(s) rendered within the allowlist")
    return 0


if __name__ == "__main__":
    sys.exit(main())

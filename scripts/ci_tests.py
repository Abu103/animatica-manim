#!/usr/bin/env python3
"""Run the whole test suite and fail unless the result is completely clean.

CI uses this instead of calling pytest directly so that "green with 32 skips"
cannot pass for a full run: no failures, no errors, no skips, no warnings, and a
plausible number of tests actually executed (a collection crash otherwise looks
like an empty, therefore clean, run).

Usage:  python scripts/ci_tests.py [extra pytest args]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

#: Anything below this means tests silently stopped being collected.
MIN_PASSED = int(os.environ.get("ANIMATICA_MIN_PASSED", "600"))

_COUNTS = re.compile(r"(\d+) (passed|failed|skipped|error|errors|warning|warnings)\b")
_NORMALISE = {"error": "errors", "errors": "errors", "warning": "warnings", "warnings": "warnings"}


def parse_summary(text: str) -> dict[str, int]:
    """Pull the counts out of pytest's final summary line."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "warnings": 0}
    for line in reversed(text.splitlines()):
        matches = _COUNTS.findall(line)
        if not matches:
            continue
        for number, word in matches:
            key = _NORMALISE.get(word, word)
            if key in counts:
                counts[key] = int(number)
        break
    return counts


def problems(counts: dict[str, int], returncode: int, text: str) -> list[str]:
    """What makes this run unacceptable."""
    found: list[str] = []
    if returncode != 0:
        found.append(f"pytest exited with {returncode}")
    if counts["failed"]:
        found.append(f"{counts['failed']} failed")
    if counts["errors"]:
        found.append(f"{counts['errors']} errors")
    if counts["skipped"]:
        found.append(f"{counts['skipped']} skipped (the environment must be complete, not partial)")
    if counts["warnings"] or "warnings summary" in text.lower():
        found.append(f"{counts['warnings'] or 'some'} warnings")
    if counts["passed"] < MIN_PASSED:
        found.append(f"only {counts['passed']} tests ran (expected at least {MIN_PASSED})")
    if "no tests ran" in text:
        found.append("no tests ran")
    return found


def main(argv: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "--strict-markers", *argv]
    print(f"$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout, end="")
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr, end="")

    counts = parse_summary(proc.stdout)
    issues = problems(counts, proc.returncode, proc.stdout)
    print(
        f"\nsummary: {counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['skipped']} skipped, {counts['errors']} errors, {counts['warnings']} warnings"
    )
    if issues:
        print("FAIL: " + "; ".join(issues))
        return 1
    print("CLEAN: every test ran, nothing failed, no warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

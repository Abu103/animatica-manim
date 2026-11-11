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
from pathlib import Path

from animatica.backends.scheduler import pick_workers, system_info

#: Anything below this means tests silently stopped being collected.
MIN_PASSED = int(os.environ.get("ANIMATICA_MIN_PASSED", "600"))

#: The most workers the suite may use. Matches the scheduler's cap; a worker
#: is a whole python process with its own Manim, so the memory runs out long
#: before the cores do.
MAX_JOBS = 12

_COUNTS = re.compile(r"(\d+) (passed|failed|skipped|error|errors|warning|warnings)\b")
_NORMALISE = {"error": "errors", "errors": "errors", "warning": "warnings", "warnings": "warnings"}


def _xdist_available() -> bool:
    """Whether pytest-xdist is installed."""
    try:
        import xdist  # noqa: F401
    except ImportError:
        return False
    return True


def suite_workers() -> tuple[int, str, int, float | None]:
    """How many workers to run the suite with, and what limited the answer.

    ``ANIMATICA_TEST_JOBS=0`` turns the parallelism off; a number sets it.
    An invalid value is ignored with a printed warning. Otherwise the count
    comes from :func:`pick_workers` (cores vs memory, capped at twelve).

    Returns ``(workers, limit, cpus, mem_gb)``.
    """
    cpus, mem = system_info()
    override = os.environ.get("ANIMATICA_TEST_JOBS")
    if override is not None and override.strip():
        try:
            wanted = int(override.strip())
        except ValueError:
            print(
                f"warning: ignoring ANIMATICA_TEST_JOBS={override!r}: not a whole number",
                file=sys.stderr,
            )
            wanted = None
        if wanted is not None:
            if wanted == 0:
                return 0, "env", cpus, mem
            return wanted, "env", cpus, mem
    workers, limit = pick_workers("test", cpus=cpus, mem_gb=mem)
    return workers, limit, cpus, mem


def suite_jobs() -> str:
    """How many workers to run the suite with (as a pytest -n string).

    Kept for callers that only need the number; :func:`suite_workers` also
    returns the limit and the machine figures behind it.
    """
    workers, _limit, _cpus, _mem = suite_workers()
    return str(max(0, workers))


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


#: Failure detail is surfaced through check annotations: job logs are not
#: readable from anywhere except a browser, annotations are.
_ANNOTATION_HEAD = re.compile(r"^(FAILED|ERROR|SKIPPED|E   )")


def _excerpt(text: str, limit: int = 12) -> list[str]:
    """The lines most worth seeing when the suite is not clean.

    Prioritize pytest's ``FAILED tests/...::test_name`` summary over traceback
    context. Otherwise a burst of ``E`` lines can consume the annotation limit
    before the actionable test names are shown in GitHub's Checks UI.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    summaries = [
        line for line in lines
        if line.strip().startswith(("FAILED ", "ERROR ", "SKIPPED "))
    ]
    details = [line for line in lines if _ANNOTATION_HEAD.match(line.strip())]
    interesting: list[str] = []
    for line in [*summaries, *details]:
        if line not in interesting:
            interesting.append(line)
    if not interesting:
        interesting = [ln for ln in lines if "warning" in ln.lower()][:limit]
    return interesting[:limit]


def annotate(text: str, issues: list[str]) -> None:
    """Emit GitHub workflow commands so CI failures are readable via the API."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    print("::error title=test suite not clean::" + "; ".join(issues)[:900])
    for line in _excerpt(text):
        print(f"::error::{line[:900]}")


def main(argv: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "-rs", "--strict-markers"]
    workers, limit, cpus, mem = suite_workers()
    mem_str = f"{mem:.1f}" if mem is not None else "?"
    print(
        f"workers: {workers} (cpus={cpus}, mem={mem_str}GB, limit={limit})",
        flush=True,
    )
    jobs = str(workers)
    if jobs != "0" and _xdist_available():
        cmd += ["-n", jobs]
    cmd += argv
    print(f"$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout, end="")
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr, end="")

    log = Path("ci-tests.log")
    log.write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")

    counts = parse_summary(proc.stdout)
    issues = problems(counts, proc.returncode, proc.stdout)
    print(
        f"\nsummary: {counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['skipped']} skipped, {counts['errors']} errors, {counts['warnings']} warnings"
    )
    if issues:
        print("FAIL: " + "; ".join(issues))
        annotate(proc.stdout + proc.stderr, issues)
        return 1
    print("CLEAN: every test ran, nothing failed, no warnings.")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::notice title=test suite clean::{counts['passed']} passed, no skips, no warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

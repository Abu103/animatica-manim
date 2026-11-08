"""The CI gate must reject a suite that quietly skips or warns."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ci_tests import _excerpt, parse_summary, problems  # noqa: E402


def test_parses_a_clean_summary():
    counts = parse_summary("..... 686 passed in 60.62s")
    assert counts["passed"] == 686
    assert counts["failed"] == counts["skipped"] == counts["errors"] == 0
    assert problems(counts, 0, "686 passed in 60s") == []


def test_parses_a_mixed_summary():
    counts = parse_summary(".... 686 passed, 32 skipped, 1 warning in 60s")
    assert counts["passed"] == 686
    assert counts["skipped"] == 32
    assert counts["warnings"] == 1


def test_skips_are_a_failure():
    counts = parse_summary("686 passed, 32 skipped in 60s")
    issues = problems(counts, 0, "686 passed, 32 skipped")
    assert any("skipped" in issue for issue in issues)


def test_warnings_are_a_failure():
    counts = parse_summary("686 passed, 2 warnings in 60s")
    issues = problems(counts, 0, "686 passed\nwarnings summary")
    assert any("warning" in issue for issue in issues)


def test_failures_and_errors_are_failures():
    counts = parse_summary("680 passed, 6 failed, 2 errors in 60s")
    issues = problems(counts, 1, "")
    assert any("failed" in i for i in issues)
    assert any("error" in i for i in issues)


def test_a_collapsed_run_cannot_pass_as_clean():
    counts = parse_summary("no tests ran in 0.01s")
    issues = problems(counts, 5, "no tests ran in 0.01s")
    assert any("no tests ran" in i for i in issues)


def test_failure_excerpt_prioritizes_test_names_over_traceback_lines():
    traceback = "\n".join(f"E   AssertionError: status is empty ({i})" for i in range(20))
    summary = "FAILED tests/test_tui.py::test_storyboard_status - AssertionError"

    excerpt = _excerpt(f"{traceback}\n{summary}", limit=3)

    assert excerpt[0] == summary
    assert len(excerpt) == 3

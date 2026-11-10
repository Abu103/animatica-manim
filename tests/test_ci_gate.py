"""The CI gate must reject a suite that quietly skips or warns."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# B4: the render gate covers the conformance corpus and its allowlist
# ---------------------------------------------------------------------------


def _allowlist_entries() -> list[tuple[str, str]]:
    """Every (component, warning kind) the allowlist still tolerates."""
    from ci_render_gate import load_allowlist

    return [
        (component, kind)
        for component, kinds in load_allowlist().items()
        for kind in kinds
    ]


def test_gate_renders_the_conformance_corpus():
    """The gate must cover the conformance corpus, not only the fixtures."""
    from ci_render_gate import storyboard_paths

    paths = storyboard_paths()
    names = {p.name for p in paths}

    assert "compare_long.json" in names, "the fixtures must stay in the gate"
    assert "timeline.json" in names, "the conformance corpus must be in the gate"
    assert "expected.json" not in names, "expected.json is not a storyboard"


def test_warning_kind_reads_the_lint_kind():
    from ci_render_gate import warning_kind

    assert warning_kind("[frame-lint] [warning] safe_area at 0.0s (scene 0): 1 px") == "safe_area"
    assert warning_kind("[frame-lint] [error] clipped at 1.0s (scene 0): 50% of an edge") == "clipped"
    assert warning_kind("timing: a beat ran 2.0s longer than its declared 3.6s") == "timing"
    assert warning_kind("compare: text scaled to 25 px (floor 32)") is None


def test_a_tolerated_warning_is_not_a_failure():
    """An allowlisted kind does not fail the gate."""
    from ci_render_gate import tolerated_reason

    allowlist = {"compare": {"small_content": "only the caption is on screen"}}

    assert tolerated_reason(["compare"], "small_content", allowlist)
    assert tolerated_reason(["compare"], "safe_area", allowlist) is None
    assert tolerated_reason(["timeline"], "small_content", allowlist) is None


def test_allowlist_entries_need_a_reason(tmp_path):
    """An allowlist entry without a reason is not accepted."""
    import json

    from ci_render_gate import load_allowlist

    path = tmp_path / "gate_allowlist.json"
    path.write_text(json.dumps({"compare": {"small_content": ""}}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_allowlist(path)


def test_the_allowlist_has_an_entry_for_every_tolerated_warning():
    """The allowlist is the record of what is still wrong; it must not be empty."""
    from ci_render_gate import load_allowlist

    allowlist = load_allowlist()

    assert allowlist, "the allowlist must record the warnings that are still there"
    for component, kinds in allowlist.items():
        assert kinds, f"{component} has an empty entry in the allowlist"


@pytest.mark.render
@pytest.mark.parametrize("component,kind", _allowlist_entries())
def test_allowlisted_warning_still_happens(component, kind, tmp_path):
    """The allowlist may only shrink.

    A tolerated warning that no longer happens has to be removed from the
    allowlist; leaving it there hides a regression behind a stale excuse.
    """
    from ci_render_gate import _render, storyboard_components, storyboard_paths, warning_kind

    found = False
    for storyboard in storyboard_paths():
        if component not in storyboard_components(storyboard):
            continue
        _code, warnings, _fallbacks = _render(storyboard, tmp_path / storyboard.stem)
        if any(warning_kind(w) == kind for w in warnings):
            found = True
            break

    assert found, (
        f"the allowlist tolerates {component}/{kind}, but it no longer happens; "
        "remove it from the allowlist"
    )

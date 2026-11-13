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


def test_the_allowlist_is_a_valid_file():
    """The allowlist is the record of what is still wrong; it must stay readable.

    It may be empty: that means nothing is tolerated and the gate is strict.
    """
    from ci_render_gate import ALLOWLIST_PATH, load_allowlist

    assert ALLOWLIST_PATH.is_file(), f"{ALLOWLIST_PATH.name} must exist"
    allowlist = load_allowlist()

    for component, kinds in allowlist.items():
        assert kinds, f"{component} has an empty entry in the allowlist"


@pytest.mark.render
def test_allowlisted_warning_still_happens(tmp_path):
    """The allowlist may only shrink.

    A tolerated warning that no longer happens has to be removed from the
    allowlist; leaving it there hides a regression behind a stale excuse.
    """
    from ci_render_gate import _render, load_allowlist, storyboard_components, storyboard_paths, warning_kind

    for component, kind in _allowlist_entries():
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


# ---------------------------------------------------------------------------
# B4c: the gate owns the conformance corpus, and it checks the durations
# ---------------------------------------------------------------------------


def test_the_gate_renders_the_whole_conformance_corpus():
    """Every storyboard the corpus promises must be rendered by the gate.

    The suite does not render the corpus any more: the gate is the one place
    where it is rendered, so the gate has to cover all of it.
    """
    import json

    from ci_render_gate import storyboard_paths

    expected = json.loads(
        (Path(__file__).resolve().parent / "conformance" / "expected.json").read_text(
            encoding="utf-8"
        )
    )
    rendered = {p.name for p in storyboard_paths()}

    assert expected, "the corpus must promise something"
    assert set(expected) <= rendered, set(expected) - rendered


def test_the_gate_fails_when_a_storyboard_does_not_keep_its_promise():
    """The gate must fail when the scene count or the duration is wrong."""
    from ci_render_gate import duration_failures

    report = {"scene_durations": [3.0]}

    assert duration_failures(report, {"scenes": 1, "duration": 3.0}) == []
    assert duration_failures(report, {"scenes": 2, "duration": 3.0})
    assert duration_failures(report, {"scenes": 1, "duration": 9.0})
    assert duration_failures(report, {}) == []


def test_the_gate_reads_what_the_corpus_promises():
    """The expected.json must be readable, or the gate checks nothing."""
    from ci_render_gate import load_expected

    expected = load_expected()

    assert expected, "expected.json must hold the promises of the corpus"
    for name, promise in expected.items():
        assert name.endswith(".json"), name
        assert "scenes" in promise, name
        assert "duration" in promise, name


def test_the_suite_runs_on_several_workers():
    """The suite is mostly render tests; it has to use the cores."""
    from ci_tests import MAX_JOBS, suite_jobs

    jobs = int(suite_jobs())

    assert 0 <= jobs <= MAX_JOBS


# --- the sandbox fast path in ci.yml ------------------------------------------------------------
import re as _re

_CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _ci_job(name: str) -> str:
    """The text of one top-level job of ci.yml (no YAML dependency: split on 2-space job keys)."""
    text = _CI.read_text(encoding="utf-8")
    m = _re.search(rf"^  {_re.escape(name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text, _re.M | _re.S)
    assert m, f"ci.yml has no job named {name}"
    return m.group(1)


def test_ci_has_the_sandbox_gate_job():
    job = _ci_job("sandbox-runtime-gate")
    assert "runtime_key.sh" in job
    assert "ls-remote" in job and "runtime-" in job
    assert "ANIMATICA_GATE_WAIT_MIN" in job  # it waits for the publishing workflow, then fails with a message


def test_gate_job_uses_runtime_key_sh():
    """One key implementation: the gate must not re-derive the key some other way."""
    job = _ci_job("sandbox-runtime-gate")
    assert "sh scripts/runtime_key.sh" in job
    assert "sha256sum" not in job


def test_ci_has_the_clean_container_timing_job():
    job = _ci_job("sandbox-fast-path")
    assert "needs: sandbox-runtime-gate" in job
    assert "container:" in job and "debian:bookworm-slim" in job
    assert "sh scripts/sandbox.sh" in job
    assert "ANIMATICA_BUDGET_S" in job
    # both network tiers: the release path and the codeload-only path
    assert "release" in job and "codeload" in job
    assert "ANIMATICA_RELEASE_BASE" in job  # forced to an unreachable host for the codeload tier


def test_fast_path_container_is_bare():
    """The point is a machine with only curl, tar and sh: no git, python, ffmpeg or apt-installed cairo."""
    job = _ci_job("sandbox-fast-path")
    installs = [ln for ln in job.splitlines() if "apt-get install" in ln]
    assert installs, "the container needs ca-certificates and curl"
    joined = " ".join(installs)
    for forbidden in ("git", "python", "ffmpeg", "cairo", "pango", "pkg-config"):
        assert forbidden not in joined, forbidden


def test_aggregate_linux_job_is_untouched():
    """The new jobs must not change what branch protection waits on."""
    job = _ci_job("linux")
    assert "needs: [linux-tests, linux-render]" in job
    assert "sandbox" not in job

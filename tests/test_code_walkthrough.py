import pytest

from animatica.components.code_walkthrough import CodeWalkthrough
from animatica.components.registry import default_registry


def test_registered():
    assert "code_walkthrough" in default_registry().names()


def test_duration_is_3s_plus_1s_per_line():
    p = CodeWalkthrough.Params(title="t", code="a = 1\nb = 2", lines=[1, 2])
    assert CodeWalkthrough().duration(p) == pytest.approx(3.0 + 1.0 * 2)


def test_duration_defaults_to_all_lines():
    p = CodeWalkthrough.Params(title="t", code="a = 1\nb = 2\nc = 3")
    assert CodeWalkthrough().duration(p) == pytest.approx(3.0 + 1.0 * 3)


def test_rejects_too_long_code():
    with pytest.raises(Exception):
        CodeWalkthrough.Params(title="t", code="x" * 301)


def test_fallback_text_contains_code_and_variables():
    p = CodeWalkthrough.Params(
        title="Walk",
        code="x = 1\ny = x + 1",
        lines=[1, 2],
        variables={"x": "1", "y": "2"},
    )
    text = CodeWalkthrough().fallback_text(p)
    assert "Walk" in text
    assert "x = 1" in text
    assert "y = x + 1" in text
    assert "x = 1" in text
    assert "y = 2" in text


def test_empty_lines_defaults_to_all():
    p = CodeWalkthrough.Params(title="t", code="a = 1\nb = 2", lines=[])
    assert CodeWalkthrough().duration(p) == pytest.approx(3.0 + 1.0 * 2)


def test_rejects_invalid_line_index():
    """Line indices must be within range of code lines."""
    with pytest.raises(Exception):
        CodeWalkthrough.Params(title="t", code="a = 1\nb = 2", lines=[3])
    with pytest.raises(Exception):
        CodeWalkthrough.Params(title="t", code="a = 1\nb = 2", lines=[0])
    with pytest.raises(Exception):
        CodeWalkthrough.Params(title="t", code="a = 1\nb = 2", lines=[-1])


def test_rejects_too_many_lines():
    """More than MAX_LINES lines to step through should be rejected."""
    code = "\n".join(f"x = {i}" for i in range(13))
    with pytest.raises(Exception):
        CodeWalkthrough.Params(title="t", code=code, lines=list(range(1, 14)))


# ---------------------------------------------------------------------------
# Render tests (require manim)
# ---------------------------------------------------------------------------

def test_code_walkthrough_render(run_component):
    """Code walkthrough should render without errors."""
    p = CodeWalkthrough.Params(
        title="Walk through",
        code="def fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)",
        language="python",
        lines=[1, 2, 3, 4],
        variables={"n": "5", "result": "8"},
    )
    scene, warnings = run_component(CodeWalkthrough(), p)
    error_warnings = [w for w in warnings if "error" in w.lower()]
    assert len(error_warnings) == 0, f"Unexpected errors: {error_warnings}"


def test_code_walkthrough_render_no_lines(run_component):
    """Code walkthrough with no lines specified (defaults to all) should render."""
    p = CodeWalkthrough.Params(
        title="Walk through",
        code="x = 1\ny = 2",
    )
    scene, warnings = run_component(CodeWalkthrough(), p)
    error_warnings = [w for w in warnings if "error" in w.lower()]
    assert len(error_warnings) == 0, f"Unexpected errors: {error_warnings}"


@pytest.mark.parametrize(
    "extra",
    [
        {"lines": [1, 2, 3, 4], "variables": {"n": "5", "result": "8"}},  # docs/gallery/code_walkthrough.json
        {"lines": [1, 2, 3, 4]},  # no variable panel: one fade-in fewer
        {"lines": [2, 4]},  # a subset of the lines
        {},  # every line
    ],
    ids=["with-variables", "no-variables", "line-subset", "all-lines"],
)
def test_code_walkthrough_beat_is_not_longer_than_its_declared_duration(run_component, extra):
    """The line holds used the whole duration and left no room for the 0.4s fade-out."""
    p = CodeWalkthrough.Params(
        title="Walk through",
        code="def fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)",
        language="python",
        **extra,
    )
    scene, warnings = run_component(CodeWalkthrough(), p)
    timing = [w for w in warnings if w.startswith("timing:")]
    assert not timing, timing

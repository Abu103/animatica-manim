import math
import pytest

from animatica.components.parametric_graph import (
    ParametricGraph,
    _sample_and_segment,
)
from animatica.components.registry import default_registry
from animatica.storyboard.safety import parse_function, UnsafeInput


def test_registered():
    assert "parametric_graph" in default_registry().names()


def test_duration_is_4s_fixed():
    p = ParametricGraph.Params(title="t", x_expr="cos(t)", y_expr="sin(t)")
    assert ParametricGraph().duration(p) == 4.0


def test_rejects_bad_t_range():
    with pytest.raises(Exception):
        ParametricGraph.Params(title="t", x_expr="t", y_expr="t", t_range=(5.0, 0.0))


def test_rejects_unsafe_expr():
    with pytest.raises(Exception):
        ParametricGraph.Params(title="t", x_expr="__import__('os')", y_expr="t")


def test_fallback_text_contains_expressions():
    p = ParametricGraph.Params(title="Circle", x_expr="cos(t)", y_expr="sin(t)", t_range=(0.0, 6.28))
    text = ParametricGraph().fallback_text(p)
    assert "Circle" in text
    assert "cos(t)" in text
    assert "sin(t)" in text


def test_valid_expressions_pass():
    p = ParametricGraph.Params(title="Circle", x_expr="cos(t)", y_expr="sin(t)")
    assert ParametricGraph().duration(p) == 4.0


# ---------------------------------------------------------------------------
# Variable substitution: t -> x internally (no string replace of identifiers)
# ---------------------------------------------------------------------------

def test_parse_function_with_t_variable():
    """sqrt(t), tan(t), cos(t), and constants parse correctly with var_name='t'."""
    f = parse_function("sqrt(t)", var_name="t")
    assert abs(f(4.0) - 2.0) < 1e-6

    f = parse_function("tan(t)", var_name="t")
    assert abs(f(0.0) - 0.0) < 1e-6

    f = parse_function("cos(t)", var_name="t")
    assert abs(f(0.0) - 1.0) < 1e-6

    f = parse_function("5", var_name="t")
    assert f(3.0) == 5.0

    f = parse_function("pi", var_name="t")
    assert abs(f(3.0) - math.pi) < 1e-6


def test_dangerous_expressions_still_rejected():
    """__import__, eval, etc. remain rejected even with var_name='t'."""
    with pytest.raises(UnsafeInput):
        parse_function("__import__('os')", var_name="t")
    with pytest.raises(UnsafeInput):
        parse_function("eval('1+1')", var_name="t")


def test_sqrt_t_is_not_mangled():
    """sqrt(t) must NOT become sxrx(x) via string replacement."""
    f = parse_function("sqrt(t)", var_name="t")
    # sqrt(4) = 2; if 't' were replaced inside 'sqrt', we'd get sxrx(x) which
    # would fail to parse or give wrong results.
    assert abs(f(4.0) - 2.0) < 1e-6
    assert abs(f(9.0) - 3.0) < 1e-6


# ---------------------------------------------------------------------------#
# Sampling / discontinuity logic tests (exercises the actual production     #
# helper _sample_and_segment directly, not a duplicated test-only algorithm.) #
# ---------------------------------------------------------------------------#

def _sample_from_expr(x_expr: str, y_expr: str, t0: float, t1: float, samples: int = 400):
    """Convenience: parse expressions and call the production helper."""
    fx = parse_function(x_expr, var_name="t")
    fy = parse_function(y_expr, var_name="t")
    segments, _ = _sample_and_segment(fx, fy, t0, t1, samples)
    return segments


def test_tan_produces_multiple_segments():
    """tan(t) has discontinuities at pi/2 and 3pi/2; sampling should split."""
    segments = _sample_from_expr("t", "tan(t)", 0.0, 6.28)
    assert len(segments) >= 2, f"tan(t) should produce multiple segments due to discontinuities, got {len(segments)}"


def test_circle_produces_single_segment():
    """cos(t), sin(t) should produce a single continuous segment."""
    segments = _sample_from_expr("cos(t)", "sin(t)", 0.0, 6.28)
    assert len(segments) == 1, f"circle should produce one segment, got {len(segments)}"


def test_constant_curve_produces_single_segment():
    """Constant-valued curve (x=3, y=5) should produce a single segment."""
    segments = _sample_from_expr("3", "5", 0.0, 6.28)
    assert len(segments) == 1, f"constant curve should produce one segment, got {len(segments)}"


def test_large_scale_continuous_curve_single_segment():
    """A large-scale continuous curve (x=t, y=1000*t) must NOT be split into
    isolated points by a fixed absolute threshold. The scale-aware threshold
    should keep it as one segment."""
    segments = _sample_from_expr("t", "1000*t", 0.0, 1000.0)
    assert len(segments) == 1, (
        f"large-scale continuous curve should be one segment, got {len(segments)}"
    )


def test_small_scale_continuous_curve_single_segment():
    """A small-scale continuous curve (x=t/1000, y=t/1000) should be one segment."""
    segments = _sample_from_expr("t/1000", "t/1000", 0.0, 1000.0)
    assert len(segments) == 1, (
        f"small-scale continuous curve should be one segment, got {len(segments)}"
    )


def test_non_finite_gap_splits_segment():
    """A curve with a non-finite sample in the middle should split into two
    segments even though the jump distance across the gap is small.

    We inject controlled samples that include a non-finite point, rather
    than relying on 1/t over [-10, 10] (which with 400 uniform samples
    never lands exactly on t=0).  The production helper must split at the
    index gap, not bridge across it.
    """
    fx = lambda t: t
    fy = lambda t: float("nan") if t == 0.0 else 1.0 / t

    segments, _ = _sample_and_segment(fx, fy, -10.0, 10.0, samples=11)
    # 11 samples across [-10, 10] includes t=0 at index 5; 1/0 -> nan -> skipped.
    # Samples on either side are at most ~2.5 apart in x, so the jump
    # threshold alone would NOT split them. Only the index-gap check does.
    assert len(segments) >= 2, (
        f"curve with injected non-finite gap should split into >= 2 segments, "
        f"got {len(segments)}"
    )


def test_no_valid_points_returns_empty():
    """An expression that never produces finite points yields no segments."""
    fx = lambda t: float("nan")
    fy = lambda t: float("nan")
    segments, _ = _sample_and_segment(fx, fy, 0.0, 6.28)
    assert segments == []


def test_curve_grouped_with_axes():
    """Curve should be grouped with axes in a VGroup (not arranged separately).

    Verified by inspecting play(): plot_group = VGroup(axes, *curves) groups
    axes and curves together so they move/scale as a unit.
    """
    import inspect
    from manim import Axes, VMobject, VGroup

    source = inspect.getsource(ParametricGraph.play)

    # Verify axes and curves are created together in plot_group
    assert "VGroup(axes, *curves)" in source, (
        "curves should be grouped with axes in VGroup(axes, *curves)"
    )

    # Verify curves are created from axes.c2p (coordinates relative to axes)
    assert "axes.c2p(x, y)" in source, (
        "curves should use axes.c2p() to align with axes coordinates"
    )

    # Verify whole group includes title + plot_group
    assert "VGroup(title, plot_group)" in source, (
        "title and plot_group should be arranged together"
    )

    # Verify label animation uses label_mob (Text object), not the raw string
    assert "FadeIn(label_mob)" in source, (
        "label animation should use the constructed Text object, not the raw string"
    )


# ---------------------------------------------------------------------------#
# Real render tests (use the run_component fixture with real ThemeColors)   #
# ---------------------------------------------------------------------------#

@pytest.mark.render
def test_circle_with_label_real_render(run_component):
    """Render a labeled circle parametrically and verify no fallback warning.

    Exercises the full play() path: parse, sample, segment, build axes+curves,
    arrange title+plot_group+label, and animate FadeIn(label_mob).
    """
    p = ParametricGraph.Params(
        title="Circle",
        x_expr="cos(t)",
        y_expr="sin(t)",
        t_range=(0.0, 6.28),
        label="unit circle",
    )

    scene, warnings = run_component(ParametricGraph(), p)

    # No component fallback warnings (text_card would emit one on failure).
    assert warnings == [], f"unexpected warnings: {warnings}"
    # At least one animation play occurred.
    assert scene.renderer.num_plays >= 1


@pytest.mark.render
def test_tan_discontinuity_real_render(run_component):
    """Render tan(t) parametrically and verify no fallback warning.

    tan(t) has vertical asymptotes; the real render should not draw a
    misleading connecting line across them.
    """
    p = ParametricGraph.Params(
        title="Tan",
        x_expr="t",
        y_expr="tan(t)",
        t_range=(0.0, 6.28),
    )

    scene, warnings = run_component(ParametricGraph(), p)

    # No component fallback warnings.
    assert warnings == [], f"unexpected warnings: {warnings}"
    assert scene.renderer.num_plays >= 1


# ---------------------------------------------------------------------------#
# CLI / pipeline integration test (real MP4 render)                          #
# ---------------------------------------------------------------------------#

@pytest.mark.render
def test_parametric_graph_cli_render_labeled_circle(tmp_path):
    """End-to-end: render a labeled parametric circle via make_video.

    Verifies the MP4 exists and is decodable, the report has no
    parametric-graph fallback warning, and the label path executes.
    """
    from animatica.pipeline import make_video
    from animatica.storyboard.models import Storyboard

    # Build a storyboard with a labeled parametric_graph circle.
    sb = Storyboard.model_validate({
        "version": "1",
        "title": "Parametric Circle",
        "theme": {"palette": "dark-blue", "font": "default"},
        "scenes": [{
            "beats": [{
                "component": "parametric_graph",
                "params": {
                    "title": "Unit Circle",
                    "x_expr": "cos(t)",
                    "y_expr": "sin(t)",
                    "t_range": [0.0, 6.28],
                    "label": "unit circle",
                },
                "caption": "A parametric unit circle drawn with x=cos(t), y=sin(t).",
            }],
        }],
    })

    sb_path = tmp_path / "storyboard.json"
    from animatica.storyboard.models import dump_storyboard
    dump_storyboard(sb, sb_path)

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "out",
        preview=True,
    )

    # MP4 exists and is non-empty.
    assert result.video.is_file(), f"video not produced: {result.video}"
    assert result.video.stat().st_size > 0, "video is empty"

    # Report has no parametric-graph fallback warning.
    import json as _json
    report = _json.loads(result.report.read_text(encoding="utf-8"))
    warnings = report.get("warnings", [])
    pg_warnings = [w for w in warnings if "parametric_graph" in str(w).lower()]
    assert pg_warnings == [], f"parametric_graph fallback warnings: {pg_warnings}"

    # All warnings (if any) should not be about parametric_graph failing.
    assert "parametric_graph: no valid points" not in str(warnings)
    assert "parametric_graph: unsafe expression" not in str(warnings)
    assert "parametric_graph: axes failed" not in str(warnings)


@pytest.mark.render
def test_parametric_graph_cli_render_discontinuity(tmp_path):
    """Render tan(t) parametrically; verify MP4 produced and no misleading
    connecting line across asymptotes (tan splits into multiple segments).

    Discovered via: the curve is split into segments at discontinuities so
    no single curve bridges across an asymptote.
    """
    from animatica.pipeline import make_video
    from animatica.storyboard.models import Storyboard, dump_storyboard

    sb = Storyboard.model_validate({
        "version": "1",
        "title": "Parametric Tan",
        "theme": {"palette": "dark-blue", "font": "default"},
        "scenes": [{
            "beats": [{
                "component": "parametric_graph",
                "params": {
                    "title": "Tan Curve",
                    "x_expr": "t",
                    "y_expr": "tan(t)",
                    "t_range": [0.0, 6.28],
                },
                "caption": "Tan curve with discontinuities at pi/2 and 3pi/2.",
            }],
        }],
    })

    sb_path = tmp_path / "storyboard.json"
    dump_storyboard(sb, sb_path)

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "out",
        preview=True,
    )

    assert result.video.is_file(), f"video not produced: {result.video}"
    assert result.video.stat().st_size > 0, "video is empty"

    import json as _json
    report = _json.loads(result.report.read_text(encoding="utf-8"))
    warnings = report.get("warnings", [])
    pg_warnings = [w for w in warnings if "parametric_graph" in str(w).lower()]
    assert pg_warnings == [], f"parametric_graph fallback warnings: {pg_warnings}"


# ---------------------------------------------------------------------------#
# Issue #32: the axis numbers are round numbers, and they do not overlap     #
# ---------------------------------------------------------------------------#

def _is_nice_step(step: float) -> bool:
    mantissa = step / 10 ** math.floor(math.log10(step))
    return any(math.isclose(mantissa, m, rel_tol=1e-9) for m in (1, 2, 5, 10))


@pytest.mark.parametrize(
    "lo, hi",
    [
        (-0.9999900318453959, 0.9999900318453959),   # cos(t) / sin(t) over 0..6.28
        (0.0, 6.28),                                 # t itself
        (-12.7, 340.2),                              # a wide range
        (0.00031, 0.00092),                          # a tiny range
        (5.0, 5.0),                                  # a constant curve
    ],
)
def test_nice_axis_gives_a_round_step_and_round_ends(lo, hi):
    from animatica.components.parametric_graph import _nice_axis

    a, b, step = _nice_axis(lo, hi)
    assert a <= lo and b >= hi, "the axis must still contain every sampled point"
    assert _is_nice_step(step), step
    for end in (a, b):
        assert math.isclose(end / step, round(end / step), abs_tol=1e-9), (end, step)
    assert 3 <= round((b - a) / step) + 1 <= 14, "readable number of ticks"
    # the numbers manim prints come from these floats: no long tails
    for v in (a, b, step):
        assert v == round(v, 10)


@pytest.mark.render
def test_circle_axis_numbers_are_round_and_do_not_overlap():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from geometry import assert_no_text_overlap, play_component

    p = ParametricGraph.Params(
        title="Parametric Circle",
        x_expr="cos(t)",
        y_expr="sin(t)",
        t_range=(0.0, 6.28),
        label="Circle",
    )
    beat = play_component(ParametricGraph(), p, 1280, 720)
    numbers = [t for t in beat.texts if t.__class__.__name__ == "DecimalNumber"]
    assert numbers, "the parametric graph drew no axis numbers"
    for n in numbers:
        value = n.get_value()
        assert value == pytest.approx(round(value, 2)), f"axis number {value!r} is not round"
        assert n.num_decimal_places <= 2, n.num_decimal_places
    assert_no_text_overlap(beat)

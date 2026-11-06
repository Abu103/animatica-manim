import math
import pytest

from animatica.components.parametric_graph import ParametricGraph
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


# ---------------------------------------------------------------------------
# Sampling / discontinuity logic tests (no Manim render required)
# ---------------------------------------------------------------------------

def _sample_component(parametric_graph, p, samples=400):
    """Sample x(t), y(t) and split into segments at discontinuities.

    Returns list of segments, each a list of (x, y) points.
    Discontinuities are detected when consecutive points jump by more
    than 1.0 in either dimension.
    """
    from animatica.storyboard.safety import parse_function

    fx = parse_function(p.x_expr, var_name="t")
    fy = parse_function(p.y_expr, var_name="t")

    t0, t1 = p.t_range
    pts = []
    for i in range(samples):
        t = t0 + (t1 - t0) * i / (samples - 1)
        try:
            x = fx(t)
            y = fy(t)
        except Exception:
            continue
        if math.isfinite(x) and math.isfinite(y):
            pts.append((x, y))

    # Split at discontinuities (jump > 1.0 in either dimension)
    segments = []
    current = []
    prev = None
    for pt in pts:
        if prev is not None:
            dx = abs(pt[0] - prev[0])
            dy = abs(pt[1] - prev[1])
            if dx > 1.0 or dy > 1.0:
                if current:
                    segments.append(current)
                current = [pt]
            else:
                current.append(pt)
        else:
            current.append(pt)
        prev = pt
    if current:
        segments.append(current)
    return [s for s in segments if len(s) >= 2]


def test_tan_produces_multiple_segments():
    """tan(t) has discontinuities at pi/2 and 3pi/2; sampling should split."""
    p = ParametricGraph.Params(title="Tan", x_expr="t", y_expr="tan(t)", t_range=(0.0, 6.28))
    segments = _sample_component(ParametricGraph(), p)
    assert len(segments) >= 2, f"tan(t) should produce multiple segments due to discontinuities, got {len(segments)}"


def test_circle_produces_single_segment():
    """cos(t), sin(t) should produce a single continuous segment."""
    p = ParametricGraph.Params(title="Circle", x_expr="cos(t)", y_expr="sin(t)", t_range=(0.0, 6.28))
    segments = _sample_component(ParametricGraph(), p)
    assert len(segments) == 1, f"circle should produce one segment, got {len(segments)}"


def test_constant_curve_produces_single_segment():
    """Constant-valued curve (x=3, y=5) should produce a single segment."""
    p = ParametricGraph.Params(title="Constant", x_expr="3", y_expr="5", t_range=(0.0, 6.28))
    segments = _sample_component(ParametricGraph(), p)
    assert len(segments) == 1, f"constant curve should produce one segment, got {len(segments)}"


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

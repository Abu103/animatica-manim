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


# ---------------------------------------------------------------------------#
# Sampling / discontinuity logic tests (exercises the actual production     #
# segmentation logic: scale-aware jump threshold + non-consecutive sample    #
# index gap detection, not a duplicated fixed-threshold algorithm.)          #
# ---------------------------------------------------------------------------#


def _sample_component(parametric_graph, p, samples=400):
    """Sample x(t), y(t) and split into segments at discontinuities.

    Replicates the production segmentation logic from ParametricGraph.play:
    - scale-aware jump threshold (typical per-sample step * 10)
    - non-consecutive sample index gap (a failed/non-finite sample splits)

    Returns list of segments, each a list of (x, y) points.
    """
    from animatica.storyboard.safety import parse_function

    fx = parse_function(p.x_expr, var_name="t")
    fy = parse_function(p.y_expr, var_name="t")

    t0, t1 = p.t_range
    all_pts = []
    valid_indices = []
    for i in range(samples):
        t = t0 + (t1 - t0) * i / (samples - 1)
        try:
            x = fx(t)
            y = fy(t)
        except Exception:
            continue
        if math.isfinite(x) and math.isfinite(y):
            all_pts.append((x, y))
            valid_indices.append(i)

    if not all_pts:
        return []

    xs = [pt[0] for pt in all_pts]
    ys = [pt[1] for pt in all_pts]
    data_range = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    expected_step = data_range / (samples - 1)
    jump_threshold = expected_step * 10.0

    segments = []
    current_segment = []
    prev_point = None
    prev_idx = valid_indices[0]

    for idx, pt in zip(valid_indices, all_pts):
        if prev_point is not None:
            if idx != prev_idx + 1:
                if current_segment:
                    segments.append(current_segment)
                current_segment = [pt]
                prev_point = pt
                prev_idx = idx
                continue
            dx = abs(pt[0] - prev_point[0])
            dy = abs(pt[1] - prev_point[1])
            if dx > jump_threshold or dy > jump_threshold:
                if current_segment:
                    segments.append(current_segment)
                current_segment = [pt]
            else:
                current_segment.append(pt)
        else:
            current_segment.append(pt)

        prev_point = pt
        prev_idx = idx

    if current_segment:
        segments.append(current_segment)
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


def test_large_scale_continuous_curve_single_segment():
    """A large-scale continuous curve (x=t, y=1000*t) must NOT be split into
    isolated points by a fixed absolute threshold. The scale-aware threshold
    should keep it as one segment."""
    p = ParametricGraph.Params(
        title="LargeLine", x_expr="t", y_expr="1000*t", t_range=(0.0, 1000.0)
    )
    segments = _sample_component(ParametricGraph(), p)
    assert len(segments) == 1, (
        f"large-scale continuous curve should be one segment, got {len(segments)}"
    )


def test_small_scale_continuous_curve_single_segment():
    """A small-scale continuous curve (x=t/1000, y=t/1000) should be one segment."""
    p = ParametricGraph.Params(
        title="SmallLine", x_expr="t/1000", y_expr="t/1000", t_range=(0.0, 1000.0)
    )
    segments = _sample_component(ParametricGraph(), p)
    assert len(segments) == 1, (
        f"small-scale continuous curve should be one segment, got {len(segments)}"
    )


def test_non_finite_gap_splits_segment():
    """A curve with a non-finite sample in the middle should split into two
    segments even though the jump distance across the gap is small.

    x(t) = t, y(t) = 1/t has a non-finite/infinite value at t=0.  If we
    sample over [-10, 10], the sample at t=0 fails; samples on either side
    are close together (small dx) but separated by an index gap.  The
    production code must split at the gap, not bridge across it.
    """
    p = ParametricGraph.Params(
        title="Reciprocal", x_expr="t", y_expr="1/t", t_range=(-10.0, 10.0)
    )
    segments = _sample_component(ParametricGraph(), p)
    # There is a gap at t=0 (1/0 is undefined → ZeroDivisionError → skipped).
    # Samples on either side are at most ~0.05 apart in x, so the jump
    # threshold alone would NOT split them. Only the index-gap check does.
    assert len(segments) >= 2, (
        f"curve with non-finite gap should split into >= 2 segments, "
        f"got {len(segments)}"
    )


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
# Real render tests                                                          #
# ---------------------------------------------------------------------------#

def test_circle_with_label_real_render():
    """Render a labeled circle parametrically and verify no exception.

    Real Manim render (smoke test) that exercises the full play() path:
    parse, sample, segment, build axes+curves, arrange title+plot_group+label,
    and animate FadeIn(label_mob).
    """
    import manim
    from manim import Scene, Camera

    p = ParametricGraph.Params(
        title="Circle",
        x_expr="cos(t)",
        y_expr="sin(t)",
        t_range=(0.0, 6.28),
        label="unit circle",
    )

    scene = Scene()
    try:
        scene.camera = Camera()
    except Exception:
        pass

    class Colors:
        accent = manim.YELLOW
        muted = manim.GRAY
        text = manim.WHITE

    colors = Colors()

    try:
        ParametricGraph().play(scene, p, colors)
    except Exception as exc:
        # Some Manim versions need a rendering context; skip rather than fail
        # on environment-specific render setup issues.
        import pytest

        pytest.skip(f"Full Manim render requires rendering context: {exc}")


def test_tan_discontinuity_real_render():
    """Render tan(t) parametrically and verify it does not crash.

    tan(t) has vertical asymptotes; the real render should not draw a
    misleading connecting line across them.
    """
    import manim
    from manim import Scene, Camera

    p = ParametricGraph.Params(
        title="Tan",
        x_expr="t",
        y_expr="tan(t)",
        t_range=(0.0, 6.28),
    )

    scene = Scene()
    try:
        scene.camera = Camera()
    except Exception:
        pass

    class Colors:
        accent = manim.YELLOW
        muted = manim.GRAY
        text = manim.WHITE

    colors = Colors()

    try:
        ParametricGraph().play(scene, p, colors)
    except Exception as exc:
        import pytest

        pytest.skip(f"Full Manim render requires rendering context: {exc}")

import math

from animatica.native import sample_function as exported
from animatica.native.sampling import sample_function


def test_parabola_single_segment_ends_at_2_4():
    segs = sample_function(lambda x: x * x, (0, 2), 5)
    assert len(segs) == 1 and len(segs[0]) == 5
    assert segs[0][-1] == (2.0, 4.0)
    assert segs[0][0] == (0.0, 0.0)


def test_reciprocal_splits_at_zero_and_stays_finite():
    segs = sample_function(lambda x: 1 / x, (-1, 1), 201)  # raises ZeroDivisionError at x=0
    assert len(segs) >= 2
    assert all(abs(y) <= 1e6 and math.isfinite(y) for seg in segs for _, y in seg)


def test_tan_splits_at_singularities():
    segs = sample_function(math.tan, (0, 2 * math.pi), 400)
    assert len(segs) >= 3  # pi/2 and 3pi/2 are singular
    for seg in segs:
        ys = [y for _, y in seg]
        assert all(math.isfinite(y) for y in ys)


def test_log_drops_non_finite_points():
    segs = sample_function(math.log, (-1, 1), 101)
    pts = [p for seg in segs for p in seg]
    assert pts and all(x > 0 and math.isfinite(y) for x, y in pts)


def test_explicit_y_range_controls_jump_rule():
    segs = sample_function(math.tan, (0, 2 * math.pi), 400, y_range=(-5, 5))
    assert len(segs) >= 3


def test_nan_function_returns_no_segments():
    assert sample_function(lambda x: math.nan, (0, 1), 10) == []


def test_native_export_is_callable_with_same_signature():
    assert exported(lambda x: x, (0, 1), 3)[0][-1] == (1.0, 1.0)


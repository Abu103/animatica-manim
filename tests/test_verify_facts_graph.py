"""V1a: the facts core and the graph component's facts.

Every expected number here was produced by running the code in this repo on
2026-11-17 and reading the result (see the comments). The facts must be
computed from the same ``_data(p)`` the drawing uses (design 5.1), and
nothing in ``animatica.verify`` may import Manim.
"""
from __future__ import annotations

import math
import subprocess
import sys

from animatica.components.graph import Graph, _data
from animatica.components.registry import default_registry
from animatica.storyboard.models import Beat
from animatica.verify.facts import Fact, facts_for

TWO_PI = 2 * math.pi


def _graph_facts(**params):
    base = {"fn": "x", "x_range": (0, 1), "y_range": (-1, 1)}
    base.update(params)
    return Graph().facts(Graph.Params(**base))


def _maxima(facts):
    return [f for f in facts if f.kind == "extremum" and "local max" in f.text]


def _minima(facts):
    return [f for f in facts if f.kind == "extremum" and "local min" in f.text]


def _one(facts, kind):
    found = [f for f in facts if f.kind == kind]
    assert len(found) == 1, f"expected exactly one {kind!r} fact, got {found}"
    return found[0]


def test_sin_range_extrema_zeros():
    facts = _graph_facts(fn="sin(x)", x_range=(0, TWO_PI), y_range=(-2, 2))

    assert _one(facts, "range").value == (-1.0, 1.0)
    assert _one(facts, "range").subject == "fn"

    # One max at pi/2 and one min at 3*pi/2; 400 samples put them at these x's.
    (maxima,) = _maxima(facts)
    (minima,) = _minima(facts)
    assert maxima.value == (1.57,)
    assert minima.value == (4.71,)
    assert "1 local maximum" in maxima.text

    # Computed: exactly one interior sign change, near pi. The left endpoint
    # sin(0) == 0 is not a sign change, and sin(2*pi) < 0, so neither end
    # contributes a zero.
    assert _one(facts, "zero").value == (3.14,)

    assert _one(facts, "clipped").value is False

    domain = _one(facts, "domain")
    assert domain.value == "plain axes"
    assert "never draws a frequency spectrum" in domain.text


def test_x_squared_clipping_uses_the_unclipped_samples():
    clipped = _graph_facts(fn="x**2", x_range=(-2, 2), y_range=(0, 1))
    assert _one(clipped, "clipped").value is True

    window = _graph_facts(fn="x**2", x_range=(-2, 2), y_range=(0, 5))
    assert _one(window, "clipped").value is False


def test_clipping_at_the_visible_limit_is_not_clipping():
    # sin's highest sample on this 400-point grid is 0.99999, so it never
    # touches the limit; x**2 touches 1.0 exactly at both x endpoints.
    sin = _graph_facts(fn="sin(x)", x_range=(0, TWO_PI), y_range=(-1, 1))
    assert _one(sin, "clipped").value is False

    parabola = _graph_facts(fn="x**2", x_range=(-1, 1), y_range=(0, 1))
    assert _one(parabola, "clipped").value is False


def test_one_ulp_above_the_limit_is_not_clipping():
    # sin^2+cos^2 is 1 everywhere, but 13 of the 400 samples evaluate to
    # 1.0000000000000002 (one ULP above 1.0). Without a tolerance the curve
    # is reported as clipped by the exact y_range that contains it.
    facts = _graph_facts(fn="sin(x)**2+cos(x)**2", x_range=(0, TWO_PI), y_range=(0, 1))
    assert _one(facts, "clipped").value is False


def test_ulp_jitter_is_not_an_extremum():
    # The same 1-ULP noise makes the strict neighbour test report 21 maxima
    # and 53 minima on a curve that is constant. Nothing that flat has peaks.
    facts = _graph_facts(fn="sin(x)**2+cos(x)**2", x_range=(0, TWO_PI), y_range=(0, 1))
    (maxima,) = _maxima(facts)
    (minima,) = _minima(facts)
    assert maxima.value == ()
    assert minima.value == ()
    assert "no local maxima" in maxima.text


def test_extremum_cap_keeps_the_true_count():
    # sin(20*x) on (0, 2*pi) has 20 maxima. The value must count all of them
    # even though the text only lists the first 8.
    facts = _graph_facts(fn="sin(20*x)", x_range=(0, TWO_PI), y_range=(-2, 2))
    (maxima,) = _maxima(facts)
    assert len(maxima.value) == 20
    assert "20 local maxima" in maxima.text
    assert "the first 8 at x = " in maxima.text

    # Same rule for zeros: 39 interior crossings on this grid, 12 listed.
    zero = _one(facts, "zero")
    assert len(zero.value) == 39
    assert "the first 12 at x = " in zero.text


def test_zero_at_a_sample_is_a_crossing():
    # x-5 on (0, 399) puts a sample exactly on every integer, so x=5 is
    # exactly 0. The neighbours are -1 and 1: a crossing, not a touch.
    facts = _graph_facts(fn="x-5", x_range=(0, 399), y_range=(-10, 400))
    assert _one(facts, "zero").value == (5.0,)


def test_zero_touch_is_not_a_crossing():
    # (x-5)^2 touches 0 at x=5 and stays positive on both sides.
    facts = _graph_facts(fn="(x-5)**2", x_range=(0, 10), y_range=(0, 30))
    assert _one(facts, "zero").value == ()


def test_runs_of_exact_zeros_count_once_or_not_at_all():
    # (2x-11-|x-5|+|x-6|)/2 is x-5 for x<5, exactly 0 on the whole interval
    # [5, 6], and x-6 for x>6. The 1-unit grid only sees x=5 and x=6 on that
    # flat stretch, so it can resolve one crossing at its start; the assertion
    # states what this grid sees, not the full continuum of zero samples.
    run = _graph_facts(
        fn="(2*x-11-abs(x-5)+abs(x-6))/2", x_range=(0, 399), y_range=(-10, 400)
    )
    assert _one(run, "zero").value == (5.0,)

    # A function that is zero everywhere has no crossing (and no peaks).
    flat = _graph_facts(fn="0", x_range=(0, 10), y_range=(-1, 1))
    assert _one(flat, "zero").value == ()
    (maxima,) = _maxima(flat)
    (minima,) = _minima(flat)
    assert maxima.value == ()
    assert minima.value == ()


def test_offset_curves_keep_their_extrema():
    # sample_function treats |y| > 1e9 as a singularity (native.sampling.HUGE),
    # so a curve centred exactly on 1e9 loses its positive half before facts
    # see it. Centring at 9e8 keeps every sample below that cutoff while still
    # exercising max|y| ~ 1e9, where a tolerance of 1e-9*max|y| (1e-3) drowned
    # the 1.2e-4 difference between a sin peak and its neighbour.
    for offset in (1000000, 9e8):
        facts = _graph_facts(
            fn=f"{offset}+sin(x)", x_range=(0, TWO_PI),
            y_range=(offset - 2, offset + 1),
        )
        (maxima,) = _maxima(facts)
        (minima,) = _minima(facts)
        assert len(maxima.value) == 1, offset
        assert len(minima.value) == 1, offset


def test_large_constant_has_no_extrema():
    # At 1e9 the noise allowance is ~1.4e-5, but identical samples differ by
    # exactly 0, so the strict comparison still keeps a flat curve quiet.
    facts = _graph_facts(fn="1e9", x_range=(0, TWO_PI), y_range=(1e9 - 1, 1e9 + 1))
    (maxima,) = _maxima(facts)
    (minima,) = _minima(facts)
    assert maxima.value == ()
    assert minima.value == ()


def test_small_amplitude_curve_keeps_its_extrema():
    # 1e-6*sin(x) peaks 1e-6 above zero and its sample-to-neighbour difference
    # at the peak is about 1e-10. A tolerance with an absolute floor of 1e-9
    # swallows it and the fact says "no local maxima" under a peak caption.
    # ULP noise scales with magnitude, so the tolerance has two parts: the
    # span term here is 1e-9 * 2e-6 = 2e-15, far above the ~1e-20 noise term,
    # and the real peak clears both.
    facts = _graph_facts(
        fn="1e-6*sin(x)", x_range=(0, TWO_PI), y_range=(-2e-6, 2e-6)
    )
    (maxima,) = _maxima(facts)
    (minima,) = _minima(facts)
    assert len(maxima.value) == 1
    assert len(minima.value) == 1
    assert "1 local maximum" in maxima.text


def test_flat_curve_near_zero_has_no_extrema():
    # A flat curve has span 0: for 1e-6 the noise term is only ~1.4e-20, and at
    # exactly 0 the whole tolerance is 0. Strict ">" keeps identical samples
    # quiet in both cases -- no absolute floor is needed.
    for fn in ("1e-6", "0"):
        facts = _graph_facts(fn=fn, x_range=(0, TWO_PI), y_range=(-2e-6, 2e-6))
        (maxima,) = _maxima(facts)
        (minima,) = _minima(facts)
        assert maxima.value == (), fn
        assert minima.value == (), fn


def test_extrema_never_straddle_a_gap():
    # 1/x splits at x=0. Both halves are monotone, so there is no extremum at
    # all -- in particular none at the gap (computed).
    facts = _graph_facts(fn="1/x", x_range=(-1, 1), y_range=(-10, 10))
    (maxima,) = _maxima(facts)
    (minima,) = _minima(facts)
    assert maxima.value == ()
    assert minima.value == ()
    assert "no local maxima" in maxima.text


def test_range_matches_data_and_play_is_not_called(monkeypatch):
    def _boom(*args, **kwargs):  # facts must never touch the renderer
        raise AssertionError("play() was called while computing facts")

    monkeypatch.setattr(Graph, "play", _boom)

    for fn, x_range, y_range in (
        ("sin(x)", (0, TWO_PI), (-2, 2)),
        ("exp(x)", (-2, 2), (-2, 10)),
        ("x**2", (-2, 2), (0, 5)),
    ):
        params = Graph.Params(fn=fn, x_range=x_range, y_range=y_range)
        segs = _data(params).segs
        ys = [y for seg in segs for _, y in seg]
        fact = _one(Graph().facts(params), "range")
        assert fact.value == (round(min(ys), 3), round(max(ys), 3))


def test_sin_plus_half_sin_three_x_maxima_count_is_recorded():
    # Computed on this code: three local maxima, at x = 0.71, 2.44, 4.71.
    # The design assumed two; the real number is three and is kept here.
    # (The curve's own derivative crosses zero six times, balanced 3/3.)
    facts = _graph_facts(fn="sin(x)+0.5*sin(3*x)", x_range=(0, TWO_PI), y_range=(-2, 2))
    (maxima,) = _maxima(facts)
    assert maxima.value == (0.71, 2.44, 4.71)
    assert len(maxima.value) == 3
    assert _one(facts, "range").value == (-1.076, 1.076)


def test_facts_for_validates_and_never_raises():
    registry = default_registry()
    beat = Beat(
        component="graph",
        params={"fn": "sin(x)", "x_range": [0, TWO_PI], "y_range": [-2, 2]},
    )
    facts = facts_for(registry, beat)
    assert facts and all(isinstance(f, Fact) for f in facts)
    assert {f.kind for f in facts} >= {"range", "extremum", "zero", "clipped", "domain"}

    assert facts_for(registry, Beat(component="no_such_component")) == []
    bad = Beat(component="graph", params={"fn": "sin(x)", "x_range": [1, 0], "y_range": [0, 1]})
    assert facts_for(registry, bad) == []
    # A component with no facts reports none.
    assert facts_for(registry, Beat(component="title_card", params={"title": "Hi"})) == []


def test_verify_package_imports_without_manim():
    code = (
        "import sys; import animatica.verify.facts; "
        "assert 'manim' not in sys.modules, 'manim was imported'"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

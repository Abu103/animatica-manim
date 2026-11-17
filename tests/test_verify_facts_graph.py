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

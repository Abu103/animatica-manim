import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from animatica.components._draw import fit
from animatica.components._latex import latex_to_plain
from animatica.components.bar_chart import BarChart
from animatica.components.graph import Graph, looks_like_math, make_label
from animatica.components.registry import default_registry
from animatica.components.theme import PALETTES
from animatica.storyboard.safety import UnsafeInput
from manim import Text

G = dict(fn="sin(x)", x_range=(-6.28, 6.28), y_range=(-1.5, 1.5), label="sine")


def test_registry_has_charts():
    assert {"graph", "bar_chart"} <= set(default_registry().names())


def test_graph_duration_is_4s():
    assert Graph().duration(Graph.Params(**G)) == 4.0


def test_graph_rejects_unsafe_function():
    for bad in ["__import__('os')", "x.real", "open('f')", "2x"]:
        with pytest.raises((ValidationError, UnsafeInput)):
            Graph.Params(**{**G, "fn": bad})


@pytest.mark.parametrize("field,val", [("x_range", (2, 1)), ("y_range", (1, 1))])
def test_graph_rejects_empty_ranges(field, val):
    with pytest.raises(ValidationError):
        Graph.Params(**{**G, field: val})


def test_bar_chart_duration():
    p = BarChart.Params(title="t", labels=["a", "b", "c"], values=[1, 2, 3])
    assert BarChart().duration(p) == pytest.approx(2.0 + 0.3 * 3)


def test_bar_chart_rejects_mismatched_lengths():
    with pytest.raises(ValidationError):
        BarChart.Params(title="t", labels=["a", "b"], values=[1])


def test_bar_chart_rejects_negative_values():
    with pytest.raises(ValidationError):
        BarChart.Params(title="t", labels=["a"], values=[-1])


def test_bar_chart_bar_count_limits():
    with pytest.raises(ValidationError):
        BarChart.Params(title="t", labels=[], values=[])
    with pytest.raises(ValidationError):
        BarChart.Params(title="t", labels=list("abcdefghijklm"), values=[1] * 13)


@pytest.mark.render
@pytest.mark.parametrize("comp,params", [
    (Graph(), Graph.Params(**G)),
    (Graph(), Graph.Params(fn="tan(x)", x_range=(0, 6.28), y_range=(-5, 5))),
    (Graph(), Graph.Params(fn="log(x)", x_range=(-1, 3), y_range=(-3, 3))),
    (BarChart(), BarChart.Params(title="Sales", labels=["Q1", "Q2", "Q3"], values=[3, 5, 2])),
])
def test_chart_renders_and_adds_mobjects(run_component, comp, params):
    scene, warnings = run_component(comp, params)
    assert warnings == []
    assert scene.renderer.num_plays >= 1
    assert scene.renderer.time == pytest.approx(comp.duration(params), abs=0.05)  # beat takes its declared time


def test_looks_like_math():
    assert looks_like_math("x^3/6")
    assert looks_like_math("y = x^2")
    assert looks_like_math(r"\sin(x)")
    assert not looks_like_math("Sine wave")
    assert not looks_like_math("Growth of terms")


# ---------------------------------------------------------------------------
# approx_fn: original + approximation together
# ---------------------------------------------------------------------------

def test_graph_accepts_approx_fn():
    """approx_fn is validated by the same safe parser and stored on params."""
    p = Graph.Params(
        fn="exp(x)", approx_fn="1 + x + x**2/2",
        x_range=(-2, 2), y_range=(0, 4),
        label="e^x", approx_label="2nd-order Taylor",
    )
    assert p.approx_fn == "1 + x + x**2/2"
    assert p.approx_label == "2nd-order Taylor"


def test_graph_rejects_unsafe_approx_fn():
    """approx_fn must also pass the safe parser when non-empty."""
    for bad in ["__import__('os')", "x.real", "open('f')"]:
        with pytest.raises((ValidationError, UnsafeInput)):
            Graph.Params(**{**G, "approx_fn": bad})


def test_graph_approx_fn_empty_is_ok():
    """Empty approx_fn means single-curve behavior (backward compatible)."""
    p = Graph.Params(**{**G, "approx_fn": ""})
    assert p.approx_fn == ""
    assert Graph().duration(p) == 4.0


def test_graph_fallback_includes_approx_fn():
    p = Graph.Params(fn="sin(x)", approx_fn="x", x_range=(-1, 1), y_range=(-1, 1))
    text = Graph().fallback_text(p)
    assert "y = sin(x)" in text and "approx y = x" in text


@pytest.mark.render
def test_graph_renders_original_and_approximation(run_component):
    """A graph with approx_fn draws both curves and produces no warnings."""
    params = Graph.Params(
        fn="exp(x)", approx_fn="1 + x + x**2/2",
        x_range=(-2, 2), y_range=(0, 8),
        label="e^x", approx_label="2nd-order Taylor",
    )
    scene, warnings = run_component(Graph(), params)
    assert warnings == []
    assert scene.renderer.num_plays >= 1
    assert scene.renderer.time == pytest.approx(4.0, abs=0.05)


@pytest.mark.render
def test_graph_single_curve_still_works(run_component):
    """Single-curve graph (no approx_fn) still renders with no warnings."""
    scene, warnings = run_component(Graph(), Graph.Params(**G))
    assert warnings == []
    assert scene.renderer.num_plays >= 1
    assert scene.renderer.time == pytest.approx(4.0, abs=0.05)


# ---------------------------------------------------------------------------
# Graph layout: no upscaling, leaves room for caption
# ---------------------------------------------------------------------------

def test_graph_fit_does_not_scale_up():
    """With scale_up=False, small graphs are not enlarged to fill the frame,
    preserving side margins."""
    from manim import config

    old_w, old_h = config.frame_width, config.frame_height
    config.frame_width = 14.22
    config.frame_height = 8.0
    try:
        from manim import Axes, VGroup
        axes = Axes(x_range=[-2, 2, 1], y_range=[0, 4, 1], x_length=6.0, y_length=3.0)
        whole = VGroup(axes)
        fit(whole, scale_up=False)  # default bounds leave caption room
        assert axes.width == 6.0, f"expected width 6.0, got {axes.width}"
    finally:
        config.frame_width = old_w
        config.frame_height = old_h


def test_graph_fit_scales_down_when_too_wide():
    """Oversized graphs are scaled down to fit within default margins."""
    from manim import config

    old_w, old_h = config.frame_width, config.frame_height
    config.frame_width = 14.22
    config.frame_height = 8.0
    try:
        from manim import Axes, VGroup
        axes = Axes(x_range=[-10, 10, 2], y_range=[-5, 5, 1], x_length=16.0, y_length=8.0)
        whole = VGroup(axes)
        fit(whole, scale_up=False)
        assert axes.width <= 14.22 - 1.0 + 1e-6, f"expected width <= 13.22, got {axes.width}"
    finally:
        config.frame_width = old_w
        config.frame_height = old_h


def test_make_label_falls_back_to_plain_text_when_latex_raises(monkeypatch):
    """F3: when MathTex raises, make_label warns and returns Text(latex_to_plain(text))."""
    import manim

    def boom(text, *args, **kwargs):
        raise RuntimeError("no LaTeX")

    monkeypatch.setattr(manim, "MathTex", boom)
    scene = SimpleNamespace(warnings=[])
    label = make_label(scene, "x^3/6", PALETTES["dark-blue"])
    assert isinstance(label, Text)
    assert label.text == latex_to_plain("x^3/6")
    assert len(scene.warnings) == 1


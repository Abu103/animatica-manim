import pytest
from pydantic import ValidationError

from animatica.components.bar_chart import BarChart
from animatica.components.graph import Graph
from animatica.components.registry import default_registry
from animatica.storyboard.safety import UnsafeInput

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


import pytest

from animatica.components.parametric_graph import ParametricGraph
from animatica.components.registry import default_registry


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

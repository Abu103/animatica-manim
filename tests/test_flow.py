import pytest

from animatica.components.flow import Flow
from animatica.components.registry import default_registry


def test_registered():
    assert "flow" in default_registry().names()


def test_duration_is_2s_plus_0_6_per_edge():
    p = Flow.Params(title="t", nodes=["A", "B", "C"], edges=[[0, 1], [1, 2]])
    assert Flow().duration(p) == pytest.approx(2.0 + 0.6 * 2)


def test_rejects_bad_edge():
    with pytest.raises(Exception):
        Flow.Params(title="t", nodes=["A", "B"], edges=[[0, 5]])


def test_rejects_too_many_edges():
    with pytest.raises(Exception):
        Flow.Params(title="t", nodes=["A", "B"], edges=[[0, 1]] * 13)


def test_fallback_text_contains_nodes():
    p = Flow.Params(title="Flow", nodes=["A", "B", "C"], edges=[[0, 1], [1, 2]])
    text = Flow().fallback_text(p)
    assert "Flow" in text
    assert "A -> B -> C" in text


def test_empty_edges_is_ok():
    p = Flow.Params(title="t", nodes=["A"])
    assert Flow().duration(p) == pytest.approx(2.0)

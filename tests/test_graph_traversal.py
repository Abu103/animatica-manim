import json

import pytest
from pydantic import ValidationError

from animatica.components.graph_traversal import GraphTraversal

BASE = {
    "title": "BFS from A",
    "nodes": ["A", "B", "C", "D", "E", "F"],
    "edges": [["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"], ["D", "E"]],
    "start": "A",
}


def params(**kw):
    return GraphTraversal.Params.model_validate({**BASE, **kw})


def test_bfs_visits_level_by_level_with_ties_broken_by_node_order():
    assert GraphTraversal.traverse(params(order="bfs")) == [
        ("A", None), ("B", "A"), ("C", "A"), ("D", "B"), ("E", "D")]


def test_dfs_goes_deep_first_and_backtracks():
    assert GraphTraversal.traverse(params(order="dfs")) == [
        ("A", None), ("B", "A"), ("D", "B"), ("C", "D"), ("E", "D")]


def test_unreachable_nodes_are_not_visited():
    assert "F" not in [n for n, _ in GraphTraversal.traverse(params())]


def test_directed_edges_only_go_one_way():
    p = params(directed=True, edges=[["B", "A"], ["A", "C"]], start="A")
    assert GraphTraversal.traverse(p) == [("A", None), ("C", "A")]


def test_layers_are_hop_distance_from_start_and_unreachable_go_last():
    assert GraphTraversal.layers(params()) == {"A": 0, "B": 1, "C": 1, "D": 2, "E": 3, "F": 4}


def test_duration_is_two_and_a_half_seconds_plus_0_6_per_visited_node():
    assert GraphTraversal().duration(params()) == pytest.approx(2.5 + 0.6 * 5)


def test_default_order_is_bfs_and_start_defaults_to_the_first_node():
    p = GraphTraversal.Params.model_validate({"title": "t", "nodes": ["X", "Y"], "edges": [["X", "Y"]]})
    assert p.order == "bfs" and p.start == "X"


@pytest.mark.parametrize("change,match", [
    ({"nodes": ["A"]}, ""),                                        # too few nodes
    ({"nodes": list("ABCDEFGHI")}, ""),                            # too many
    ({"nodes": ["A", "a", "B"]}, "differ"),
    ({"edges": [["A", "Z"]]}, "Z"),                                # unknown node
    ({"edges": [["A", "A"]]}, "itself"),
    ({"edges": [["A", "B"], ["B", "A"]]}, "twice"),                # duplicate undirected edge
    ({"start": "Q"}, "Q"),
    ({"order": "dijkstra"}, ""),
    ({"nodes": ["ABCDE", "B"], "edges": [], "start": "B"}, ""),    # label too long
])
def test_bad_params_are_rejected(change, match):
    with pytest.raises(ValidationError, match=match or None):
        params(**change)


def test_two_directed_edges_between_the_same_pair_are_distinct():
    params(directed=True, edges=[["A", "B"], ["B", "A"]])


def test_fallback_text_gives_the_visit_order():
    assert GraphTraversal().fallback_text(params()).splitlines() == ["BFS from A", "A → B → C → D → E"]


def test_schema_is_json_serialisable():
    json.dumps(GraphTraversal.Params.model_json_schema())

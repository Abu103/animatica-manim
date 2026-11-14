
from animatica.native.layout import layout_graph


def test_layout_is_deterministic():
    nodes = ["a", "b", "c"]
    edges = [("a", "b"), ("b", "c")]
    pos1 = layout_graph(nodes, edges, 10.0, 5.0)
    pos2 = layout_graph(nodes, edges, 10.0, 5.0)
    assert pos1 == pos2


def test_nodes_inside_frame():
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b")]
    pos = layout_graph(nodes, edges, 10.0, 5.0)
    for x, y in pos.values():
        assert 0 <= x <= 10.0
        assert 0 <= y <= 5.0


def test_no_shared_positions():
    nodes = ["a", "b", "c", "d", "e"]
    edges = [("a", "b"), ("b", "c")]
    pos = layout_graph(nodes, edges, 10.0, 5.0)
    assert len(set(pos.values())) == len(nodes)


def test_chain_has_increasing_x():
    nodes = ["a", "b", "c"]
    edges = [("a", "b"), ("b", "c")]
    pos = layout_graph(nodes, edges, 10.0, 5.0)
    assert pos["a"][0] < pos["b"][0] < pos["c"][0]


def test_empty_edges_still_layouts():
    nodes = ["a", "b"]
    pos = layout_graph(nodes, [], 10.0, 5.0)
    assert set(pos) == {"a", "b"}


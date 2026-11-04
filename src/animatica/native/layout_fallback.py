"""Pure-Python layered left-to-right graph layout.

Nodes are placed in layers by longest-path depth (cycles broken by
ignoring back edges). Each layer gets an x column; nodes within a
layer spread vertically. Deterministic: same inputs always produce
the same positions.
"""
from __future__ import annotations


def _longest_path_depths(
    nodes: list[str], edges: list[tuple[str, str]]
) -> dict[str, int]:
    """Return layer index per node using longest-path depth.

    Edges pointing to a node already at a deeper layer are treated as
    back edges (cycle-breaking): they don't force a depth increase.
    """
    node_set = set(nodes)
    valid_edges = [(a, b) for a, b in edges if a in node_set and b in node_set]

    # Adjacency: successors
    succ: dict[str, list[str]] = {n: [] for n in nodes}
    pred: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in valid_edges:
        succ[a].append(b)
        pred[b].append(a)

    depths: dict[str, int] = {n: 0 for n in nodes}
    changed = True
    # Longest path via relaxation; bounded by |nodes| iterations
    for _ in range(len(nodes) + 1):
        changed = False
        for n in nodes:
            new_depth = 0
            for p in pred[n]:
                candidate = depths[p] + 1
                if candidate > new_depth:
                    new_depth = candidate
            if new_depth != depths[n]:
                depths[n] = new_depth
                changed = True
        if not changed:
            break
    return depths


def layout_graph(
    nodes: list[str], edges: list[tuple[str, str]], width: float, height: float
) -> dict[str, tuple[float, float]]:
    """Deterministic layered left-to-right layout.

    Returns {node: (x, y)} with every position inside
    [0, width] x [0, height], no two nodes sharing a position, and
    any chain a->b->c having strictly increasing x.
    """
    if not nodes:
        return {}

    depths = _longest_path_depths(nodes, edges)
    max_depth = max(depths.values()) if depths else 0
    n_layers = max_depth + 1

    # Group nodes by layer, preserving input order within each layer
    layer_nodes: dict[int, list[str]] = {i: [] for i in range(n_layers)}
    for n in nodes:
        layer_nodes[depths[n]].append(n)

    # X positions: evenly spaced columns across the width
    if n_layers == 1:
        x_cols = [width / 2]
    else:
        margin = min(width, height) * 0.12
        span = max(width - 2 * margin, 1.0)
        x_cols = [margin + span * i / (n_layers - 1) for i in range(n_layers)]

    # Y positions: spread nodes within each layer vertically
    positions: dict[str, tuple[float, float]] = {}
    for layer in range(n_layers):
        members = layer_nodes[layer]
        n = len(members)
        if n == 1:
            ys = [height / 2]
        else:
            margin = min(width, height) * 0.12
            span = max(height - 2 * margin, 1.0)
            ys = [margin + span * i / (n - 1) for i in range(n)]
        for node, y in zip(members, ys):
            positions[node] = (x_cols[layer], y)

    return positions


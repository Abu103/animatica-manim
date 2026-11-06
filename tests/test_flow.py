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


def test_rejects_self_loop():
    """Self-loop edges (from == to) should be rejected."""
    with pytest.raises(Exception):
        Flow.Params(title="t", nodes=["A", "B"], edges=[[0, 0]])
    with pytest.raises(Exception):
        Flow.Params(title="t", nodes=["A", "B"], edges=[[1, 1]])


def test_flow_render_simple(run_component):
    """Simple flow should render without errors."""
    p = Flow.Params(title="Flow", nodes=["A", "B", "C"], edges=[[0, 1], [1, 2]])
    scene, warnings = run_component(Flow(), p)
    # Render should succeed without errors
    error_warnings = [w for w in warnings if "error" in w.lower()]
    assert len(error_warnings) == 0, f"Unexpected errors: {error_warnings}"


def test_flow_render_larger_graph(run_component):
    """Larger flow graph should render without errors."""
    p = Flow.Params(
        title="Process",
        nodes=["Start", "Process", "Decision", "End"],
        edges=[[0, 1], [1, 2], [2, 3]],
    )
    scene, warnings = run_component(Flow(), p)
    error_warnings = [w for w in warnings if "error" in w.lower()]
    assert len(error_warnings) == 0, f"Unexpected errors: {error_warnings}"


def test_flow_render_backward_edge(run_component):
    """Backward edges (from > to) should render without errors."""
    p = Flow.Params(
        title="Loop",
        nodes=["A", "B", "C"],
        edges=[[0, 1], [1, 2], [2, 0]],  # 2->0 is a backward edge
    )
    scene, warnings = run_component(Flow(), p)
    error_warnings = [w for w in warnings if "error" in w.lower()]
    assert len(error_warnings) == 0, f"Unexpected errors: {error_warnings}"


def test_flow_render_vertical(tmp_path):
    """Flow should render in portrait (9:16) orientation."""
    from animatica.pipeline import make_video
    from animatica.storyboard.models import Storyboard

    sb = Storyboard.model_validate({
        "version": "1",
        "title": "Flow",
        "scenes": [{
            "beats": [{
                "component": "flow",
                "params": {
                    "title": "Process",
                    "nodes": ["Start", "Process", "End"],
                    "edges": [[0, 1], [1, 2]],
                }
            }]
        }]
    })

    sb_path = tmp_path / "storyboard.json"
    sb_path.write_text(sb.model_dump_json())

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "out",
        preview=True,
        vertical=True,
    )

    assert result.video.is_file()
    assert result.video.stat().st_size > 0

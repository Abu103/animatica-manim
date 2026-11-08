import pytest

from animatica.components.flow import Flow
from animatica.components.registry import default_registry
from animatica.components.theme import PALETTES


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


def test_rejects_duplicate_edges():
    """Duplicate edges (same direction) should be rejected in play()."""
    from unittest.mock import patch

    p = Flow.Params(title="t", nodes=["A", "B", "C"], edges=[[0, 1], [0, 1]])
    mock_scene = type("S", (), {"mobjects": [], "warnings": [], "play": lambda *a, **k: None, "camera": type("C", (), {"background_color": "#000"})()})()

    class MockClock:
        def __init__(self, scene, total):
            self.scene = scene
            self.total = total
            self.used = 0.0

        def play(self, *animations, run_time=1.0):
            self.used += run_time
            for anim in animations:
                mobj = getattr(anim, "mobject", None)
                if mobj is not None:
                    self.scene.mobjects.append(mobj)

        def wait(self, seconds):
            self.used += seconds

        def finish(self, fade_out=0.4):
            pass

    with patch("animatica.components.flow.Clock", MockClock):
        with pytest.raises(Exception, match="duplicate edge"):
            Flow().play(mock_scene, p, PALETTES["dark-blue"])


def test_flow_arrow_forward_geometry():
    """Forward edges (from < to) go from source bottom to destination top."""
    from unittest.mock import patch

    from manim import Arrow

    p = Flow.Params(title="Flow", nodes=["A", "B", "C"], edges=[[0, 1], [1, 2]])

    class MockScene:
        def __init__(self):
            self.mobjects = []
            self.warnings = []
            self.camera = type("Camera", (), {"background_color": "#000000"})()

        def play(self, *animations, run_time=1.0):
            for anim in animations:
                mobj = getattr(anim, "mobject", None)
                if mobj is not None:
                    self.mobjects.append(mobj)

    class MockClock:
        def __init__(self, scene, total):
            self.scene = scene
            self.total = total
            self.used = 0.0

        def play(self, *animations, run_time=1.0):
            self.used += run_time
            for anim in animations:
                mobj = getattr(anim, "mobject", None)
                if mobj is not None:
                    self.scene.mobjects.append(mobj)

        def wait(self, seconds):
            self.used += seconds

        def finish(self, fade_out=0.4):
            pass

    mock_scene = MockScene()
    with patch("animatica.components.flow.Clock", MockClock):
        Flow().play(mock_scene, p, PALETTES["dark-blue"])

    arrows = [m for m in mock_scene.mobjects if isinstance(m, Arrow)]
    assert len(arrows) == 2, f"expected 2 arrows, got {len(arrows)}"

    # Both edges are forward (0->1, 1->2): from node above to node below
    # Forward arrows go from higher y (source) to lower y (destination)
    for i, arrow in enumerate(arrows):
        start = arrow.get_start()
        end = arrow.get_end()
        # Forward edges go from higher y (source) to lower y (destination)
        assert start[1] > end[1], f"arrow {i} goes from {start[1]} to {end[1]}, expected top->bottom"
        assert start[1] - end[1] > 0.1, f"arrow {i} length too short: {start[1] - end[1]}"


def test_flow_arrow_backward_geometry():
    """Backward edges (from > to) go from source bottom to destination top.

    For a backward edge, the source node is BELOW the destination node, so the
    arrow goes from a lower y (source top) to a higher y (destination bottom),
    pointing upward (backward) toward the earlier node.
    """
    from unittest.mock import patch

    from manim import Arrow

    p = Flow.Params(title="Flow", nodes=["A", "B", "C"], edges=[[0, 1], [1, 2], [2, 0]])

    class MockScene:
        def __init__(self):
            self.mobjects = []
            self.warnings = []
            self.camera = type("Camera", (), {"background_color": "#000000"})()

        def play(self, *animations, run_time=1.0):
            for anim in animations:
                mobj = getattr(anim, "mobject", None)
                if mobj is not None:
                    self.mobjects.append(mobj)

    class MockClock:
        def __init__(self, scene, total):
            self.scene = scene
            self.total = total
            self.used = 0.0

        def play(self, *animations, run_time=1.0):
            self.used += run_time
            for anim in animations:
                mobj = getattr(anim, "mobject", None)
                if mobj is not None:
                    self.scene.mobjects.append(mobj)

        def wait(self, seconds):
            self.used += seconds

        def finish(self, fade_out=0.4):
            pass

    mock_scene = MockScene()
    with patch("animatica.components.flow.Clock", MockClock):
        Flow().play(mock_scene, p, PALETTES["dark-blue"])

    arrows = [m for m in mock_scene.mobjects if isinstance(m, Arrow)]
    assert len(arrows) == 3, f"expected 3 arrows, got {len(arrows)}"

    # Arrow 2 (2->0): backward edge from node 2 (bottom) to node 0 (top)
    # Node 2 is below node 0, so the arrow goes from lower y to higher y.
    arrow2 = arrows[2]
    start2 = arrow2.get_start()
    end2 = arrow2.get_end()
    # Backward edge (2->0): source is below, so arrow goes from lower y to higher y
    assert start2[1] < end2[1], f"backward arrow 2->0 goes from {start2[1]} to {end2[1]}, expected bottom->top"
    # The arrow should point upward (backward in the diagram, i.e. from bottom to top)
    assert end2[1] - start2[1] > 0.1, f"backward arrow too short: {end2[1] - start2[1]}"


def test_flow_render_vertical(tmp_path):
    """Flow should render in portrait (9:16) orientation."""
    from animatica.pipeline import make_video
    from animatica.storyboard.models import Storyboard

    sb = Storyboard.model_validate({
        "version": "1",
        "title": "Flow",
        "scenes": [{"beats": [{"component": "flow",
                               "params": {"title": "Process",
                                          "nodes": ["Start", "Process", "End"],
                                          "edges": [[0, 1], [1, 2]]}}]}]
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

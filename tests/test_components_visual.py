import pytest

from animatica.components.code_highlight import CodeHighlight
from animatica.components.diagram import Diagram
from animatica.components.shape_morph import ShapeMorph
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
)


def test_shape_morph_duration():
    p = ShapeMorph.Params(from_shape="circle", to_shape="square")
    assert ShapeMorph().duration(p) == 3.0


def test_diagram_duration():
    p = Diagram.Params(nodes=["a", "b"], edges=[("a", "b")])
    assert Diagram().duration(p) == pytest.approx(1.0 + 0.6 * 1)


def test_diagram_rejects_unknown_edge_node():
    with pytest.raises(Exception):
        Diagram.Params(nodes=["a"], edges=[("a", "nope")])


def test_code_highlight_duration():
    p = CodeHighlight.Params(code="print(1)\nprint(2)", lines=[1])
    assert CodeHighlight().duration(p) == pytest.approx(3.0 + 1.0 * 1)


def test_code_highlight_rejects_line_beyond_code():
    with pytest.raises(Exception):
        CodeHighlight.Params(code="print(1)", lines=[5])


@pytest.mark.render
def test_shape_morph_plays(run_component):
    s, warnings = run_component(
        ShapeMorph(),
        ShapeMorph.Params(from_shape="circle", to_shape="square"),
    )
    assert s.renderer.num_plays >= 1
    assert warnings == []


@pytest.mark.render
def test_diagram_plays(run_component):
    s, warnings = run_component(
        Diagram(),
        Diagram.Params(nodes=["a", "b", "c"], edges=[("a", "b"), ("b", "c")]),
    )
    assert s.renderer.num_plays >= 1
    assert warnings == []


@pytest.mark.render
def test_code_highlight_plays(run_component):
    s, warnings = run_component(
        CodeHighlight(),
        CodeHighlight.Params(code="print('hello')", lines=[1]),
    )
    assert s.renderer.num_plays >= 1
    assert warnings == []


@pytest.mark.render
def test_diagram_ten_node_chain_fits_frame_and_time(run_component):
    """Regression: layout coordinates used to be drawn un-centred (off the right edge) and 10 nodes overran the beat."""

    nodes = [f"Term {i}" for i in range(10)]
    edges = [(nodes[i], nodes[i + 1]) for i in range(9)]
    s, warnings = run_component(Diagram(), Diagram.Params(nodes=nodes, edges=edges))
    assert warnings == []  # includes the timing-overrun warning from Clock.finish


# ---------------------------------------------------------------------------
# B4: the code highlight has to fit the frame, keep its text apart and fit its clock
# ---------------------------------------------------------------------------


def _code_params() -> CodeHighlight.Params:
    """The parameters of the conformance storyboard, tests/conformance/code_highlight.json."""
    return CodeHighlight.Params(code="print('hello')", language="python", lines=[1])


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_code_highlight_content_stays_inside_the_safe_area(width, height):
    """The code block must stay inside the safe-area margin.

    It was scaled up to fill the frame and left off-centre, so it ran over
    the left edge of the frame and into the margin.
    """
    beat = play_component(CodeHighlight(), _code_params(), width, height)

    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_code_highlight_text_does_not_overlap(width, height):
    """The code and the line numbers must not land on each other."""
    beat = play_component(CodeHighlight(), _code_params(), width, height)

    assert_no_text_overlap(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_code_highlight_beat_fits_its_declared_duration(width, height):
    """The animations must fit inside the duration the component declared."""
    beat = play_component(CodeHighlight(), _code_params(), width, height)

    assert_beat_timing(beat)

"""T14: the graph's legend, its tick labels and its clock.

Three defects the owner saw when asking for a Taylor series:

* the legend was missing whenever the two curves were not both labelled, so
  the viewer could not tell the approximation from the function;
* the legend could leave the safe area and land on the axis numbers;
* the graph did not know how tall the caption was, so the x-axis tick labels
  ended up under it, and a curve that is clipped into many pieces made the
  beat longer than it declared.

The rules are checked against real mobjects at both resolutions, with the
real caption the renderer burns in -- not a constant.
"""
import math

import pytest

from animatica.components._draw import (
    MIN_FONT_SIZE,
    SAFE_AREA_MARGIN,
    caption_band_top,
    make_caption,
)
from animatica.components._latex import latex_to_plain
from animatica.components.graph import Graph, latex_expression
from animatica.components.theme import PALETTES
from geometry import (
    RESOLUTIONS,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
    resolution,
)

#: The conformance storyboard's graph: a function and its 2nd-order Taylor
#: approximation, as tests/conformance/graph_taylor.json draws it.
TAYLOR = dict(
    fn="exp(x)",
    approx_fn="1 + x + x**2/2",
    x_range=(-2, 2),
    y_range=(-1.5, 8),
)

ONE_LINE = "The linear approximation touches e^x at zero."
TWO_LINES = (
    "Adding the quadratic term brings the curve much closer to e^x across a "
    "wider range of x values."
)
THREE_LINES = (
    "Positive charges gather at the cloud's top, negative charges gather at "
    "its base, and the ground below turns positive again once the storm has "
    "passed overhead."
)

#: A curve that leaves the y-range and comes back: it is drawn as many
#: separate segments, and every one of them is an animation.
MANY_SEGMENTS = dict(fn="cos(x)", x_range=(-20, 20), y_range=(-0.5, 0.5))


def _caption(text: str):
    """The caption mobject the scene builds for a beat."""
    return make_caption(text, PALETTES["dark-blue"])


def _tick_labels(beat):
    """The axis number labels: one mobject per number, not per glyph."""
    return [t for t in beat.texts if t.__class__.__name__ == "DecimalNumber"]


def _legend_texts(beat):
    """The legend's texts: plain Text, unlike the axis numbers (DecimalNumber)."""
    return [t for t in beat.texts if t.__class__.__name__ == "Text"]


def _safe_box(width, height):
    margin_x = width * SAFE_AREA_MARGIN
    margin_y = height * SAFE_AREA_MARGIN
    return (
        -width / 2 + margin_x,
        width / 2 - margin_x,
        -height / 2 + margin_y,
        height / 2 - margin_y,
    )


# ---------------------------------------------------------------------------
# (a) a graph with two curves has a legend, and the legend is on screen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width,height", RESOLUTIONS)
@pytest.mark.parametrize(
    "labels",
    [
        dict(label="e^x", approx_label="2nd-order Taylor"),
        dict(label="e^x"),
        dict(approx_label="2nd-order Taylor"),
        dict(),
    ],
    ids=["both", "label", "approx-label", "none"],
)
def test_a_two_curve_graph_has_a_legend(width, height, labels):
    """Two curves on screen, and the viewer can tell which is which.

    The legend was only built when the model had labelled *both* curves, so
    a graph that compared two functions without labels showed two coloured
    curves and nothing to tell them apart.
    """
    comp = Graph()
    with resolution(width, height):
        beat = play_component(comp, Graph.Params(**TAYLOR, **labels), width, height)

    legend = getattr(comp, "last_legend", None)
    assert legend is not None, (
        "the graph drew two curves but no legend, so the viewer cannot tell "
        "the approximation from the function"
    )
    assert legend.width > 0 and legend.height > 0, "the legend is empty"

    # The legend is really on screen: its texts are among the drawn texts.
    # ``get_family`` rather than ``family_members_with_points``: a Text keeps
    # its points on its glyphs, so the latter skips the Text itself.
    drawn = {id(t) for t in beat.texts}
    legend_texts = [t for t in legend.get_family()
                    if t.__class__.__name__ in ("Text", "MathTex")]
    assert legend_texts, "the legend has no text"
    assert any(id(t) in drawn for t in legend_texts), (
        "the legend was built but never drawn"
    )


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_the_legend_names_both_curves(width, height):
    """The legend has one entry per curve."""
    comp = Graph()
    with resolution(width, height):
        play_component(
            comp,
            Graph.Params(**TAYLOR, label="e^x", approx_label="2nd-order Taylor"),
            width,
            height,
        )

    legend = getattr(comp, "last_legend", None)
    assert legend is not None
    # ``get_family``: a Text keeps its points on its glyphs, so
    # ``family_members_with_points`` skips the Text itself.
    entries = [t for t in legend.get_family()
               if t.__class__.__name__ in ("Text", "MathTex")]
    assert len(entries) == 2, f"the legend has {len(entries)} entries, not 2"
    # A math entry is LaTeX source; its plain reading is what the viewer sees.
    contents = [getattr(t, "text", None) or latex_to_plain(getattr(t, "tex_string", ""))
                for t in entries]
    assert any("e^x" in c for c in contents), contents
    assert any("Taylor" in c for c in contents), contents


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_the_legend_stays_inside_the_safe_area(width, height):
    """A long legend label must not push the legend out of the frame.

    The legend was moved to the corner of the axes without looking at its own
    width, so a long label put it past the safe-area margin and frame-lint
    warned about every frame of the video.
    """
    long_label = "a very long legend label that stretches across the whole plot"
    comp = Graph()
    with resolution(width, height):
        play_component(
            comp,
            Graph.Params(**TAYLOR, label=long_label, approx_label=long_label),
            width,
            height,
        )

    legend = getattr(comp, "last_legend", None)
    assert legend is not None
    left, right, bottom, top = _safe_box(width, height)
    assert legend.get_left()[0] >= left - 1e-6, (
        f"the legend starts at x={legend.get_left()[0]:.3f}, outside the safe "
        f"area x={left:.3f}"
    )
    assert legend.get_right()[0] <= right + 1e-6, (
        f"the legend ends at x={legend.get_right()[0]:.3f}, outside the safe "
        f"area x={right:.3f}"
    )
    assert legend.get_bottom()[1] >= bottom - 1e-6
    assert legend.get_top()[1] <= top + 1e-6


# ---------------------------------------------------------------------------
# (b) the tick labels stay above the caption
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width,height", RESOLUTIONS)
@pytest.mark.parametrize(
    "caption_text", [ONE_LINE, TWO_LINES, THREE_LINES], ids=["1-line", "2-lines", "3-lines"]
)
def test_the_tick_labels_stay_above_the_caption(width, height, caption_text):
    """The x-axis numbers must not end up under the caption.

    The graph reserved a fixed 3.0 units for the caption instead of measuring
    it, so a caption that wrapped onto a third line rose into the axis
    numbers.
    """
    comp = Graph()
    with resolution(width, height):
        caption = _caption(caption_text)
        beat = play_component(
            comp, Graph.Params(**TAYLOR, label="e^x", approx_label="2nd-order Taylor"),
            width,
            height,
            caption=caption,
        )

    ticks = _tick_labels(beat)
    assert ticks, "the graph drew no axis numbers"
    caption_top = caption.get_top()[1]
    for tick in ticks:
        assert tick.get_bottom()[1] >= caption_top + 0.1, (
            f"the axis number at x={tick.get_center()[0]:.2f} has its bottom at "
            f"y={tick.get_bottom()[1]:.3f}, under the caption's top "
            f"y={caption_top:.3f}"
        )

    # The content also stays inside the safe area.
    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_the_graph_reserves_room_for_the_real_caption(width, height):
    """A taller caption leaves less room for the plot.

    The band the graph works against is derived from the caption the renderer
    burns in, so a two-line caption and a three-line caption cannot both be
    satisfied by one hardcoded number.
    """
    comp = Graph()
    with resolution(width, height):
        one = _caption(ONE_LINE)
        three = _caption(THREE_LINES)
        assert caption_band_top(three) > caption_band_top(one), (
            "a three-line caption must leave less room than a one-line one"
        )
        beat_one = play_component(
            comp, Graph.Params(**TAYLOR, label="e^x", approx_label="2nd-order Taylor"),
            width, height, caption=one,
        )
        beat_three = play_component(
            Graph(), Graph.Params(**TAYLOR, label="e^x", approx_label="2nd-order Taylor"),
            width, height, caption=three,
        )

    bottom_one = min(t.get_bottom()[1] for t in _tick_labels(beat_one))
    bottom_three = min(t.get_bottom()[1] for t in _tick_labels(beat_three))
    assert bottom_three > bottom_one, (
        f"a three-line caption must push the axis numbers up: {bottom_one:.3f} "
        f"-> {bottom_three:.3f}"
    )


# ---------------------------------------------------------------------------
# (c) no text lands on other text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width,height", RESOLUTIONS)
@pytest.mark.parametrize(
    "labels",
    [
        dict(label="a very long legend label that stretches across the whole plot",
             approx_label="a very long legend label that stretches across the whole plot"),
        dict(),
    ],
    ids=["long-labels", "no-labels"],
)
def test_no_text_overlaps_another_text(width, height, labels):
    """The legend must not land on the axis numbers.

    The legend was anchored to the corner of the axes without knowing how wide
    it was, so a long label grew across the plot and over the y-axis numbers.
    The same happened without labels: a curve named by its own expression is
    long enough to reach the numbers, which is the case the rendered
    storyboard hit.
    """
    comp = Graph()
    with resolution(width, height):
        beat = play_component(
            comp,
            Graph.Params(**TAYLOR, **labels),
            width,
            height,
            caption=_caption(THREE_LINES),
        )

    assert_no_text_overlap(beat)


# ---------------------------------------------------------------------------
# (d) the beat ends when it says it does
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fps", [15, 30, 60])
def test_the_beat_does_not_overrun_its_declared_duration(fps):
    """The video must not be longer than the beat declares.

    Manim rounds every animation up to a whole frame, so a run time that is
    not a whole number of frames makes the video longer than the beat. The
    graph gave every one of a curve's segments the same slice of time, and
    the rounding of those slices added up: a curve clipped into many pieces
    made the beat 0.2s longer than the 4.0s it declared.
    """
    from manim import tempconfig

    with tempconfig({"frame_rate": fps}):
        beat = play_component(Graph(), Graph.Params(**MANY_SEGMENTS), 1280, 720)

    frames = sum(math.ceil(rt * fps - 1e-9) for rt in beat.scene.played_run_times)
    frames += sum(math.ceil(w * fps - 1e-9) for w in beat.scene.waited_seconds)
    allowed = math.ceil(beat.duration * fps)

    assert frames <= allowed, (
        f"at {fps} fps the video is {frames / fps:.3f}s long ({frames} frames) "
        f"but the beat declares {beat.duration}s ({allowed} frames allowed)"
    )


@pytest.mark.parametrize("fps", [15, 30, 60])
def test_the_two_curve_graph_also_fits_its_declared_duration(fps):
    """The same holds for the graph the conformance storyboard renders."""
    from manim import tempconfig

    with tempconfig({"frame_rate": fps}):
        beat = play_component(
            Graph(),
            Graph.Params(**TAYLOR, label="e^x", approx_label="2nd-order Taylor"),
            1280,
            720,
        )

    frames = sum(math.ceil(rt * fps - 1e-9) for rt in beat.scene.played_run_times)
    frames += sum(math.ceil(w * fps - 1e-9) for w in beat.scene.waited_seconds)
    allowed = math.ceil(beat.duration * fps)

    assert frames <= allowed, (
        f"at {fps} fps the video is {frames / fps:.3f}s long ({frames} frames) "
        f"but the beat declares {beat.duration}s ({allowed} frames allowed)"
    )


# ---------------------------------------------------------------------------
# (e) the legend is placed where the curves are not
# ---------------------------------------------------------------------------

#: The three beats the owner asked about, as tests/conformance/graph_taylor.json
#: draws them: a function with its 1st-order, 2nd-order and four-term Taylor
#: approximations, each with the caption the storyboard burns in.
STORYBOARDS = [
    (
        "1st-order",
        {**TAYLOR, "approx_fn": "1 + x", "label": "e^x",
         "approx_label": "1st-order Taylor"},
        ONE_LINE,
    ),
    (
        "2nd-order",
        {**TAYLOR, "label": "e^x", "approx_label": "2nd-order Taylor"},
        TWO_LINES,
    ),
    (
        "four-terms",
        {**TAYLOR, "approx_fn": "1 + x + x**2/2 + x**3/6 + x**4/24"},
        THREE_LINES,
    ),
]


def _curve_points(beat):
    """Every sampled point of every curve the beat drew, in frame coordinates."""
    points = []
    for mob in beat.mobjects:
        # The curves are raw VMobjects; the axes and the legend are groups.
        if mob.__class__.__name__ != "VMobject":
            continue
        # ``.points`` (Nx3) rather than ``get_points()``: Manim routes the
        # get_* form through a deprecated shim, and the suite treats warnings
        # as errors.
        for x, y, *_ in mob.points:
            points.append((float(x), float(y)))
    return points


def _point_inside(point, mob, inflate: float = 0.05) -> bool:
    return (
        mob.get_left()[0] - inflate <= point[0] <= mob.get_right()[0] + inflate
        and mob.get_bottom()[1] - inflate <= point[1] <= mob.get_top()[1] + inflate
    )


@pytest.mark.parametrize("width,height", RESOLUTIONS)
@pytest.mark.parametrize("name,params,captions", STORYBOARDS, ids=[s[0] for s in STORYBOARDS])
def test_the_legend_never_sits_on_a_curve(width, height, name, params, captions):
    """No point of any curve may fall inside the legend's box.

    The legend was anchored to the plot's top-right corner unconditionally,
    and on a rising curve (e^x) that corner is exactly where the curve goes:
    the rendered legend had the cyan line running through its second entry.
    The placement must look at where the curves actually are.
    """
    comp = Graph()
    with resolution(width, height):
        beat = play_component(
            comp, Graph.Params(**params), width, height, caption=_caption(captions)
        )

    legend = getattr(comp, "last_legend", None)
    assert legend is not None
    hits = [p for p in _curve_points(beat) if _point_inside(p, legend)]
    assert not hits, (
        f"{name}: {len(hits)} sampled curve point(s) lie inside the legend, "
        f"first at ({hits[0][0]:.2f}, {hits[0][1]:.2f}); legend is at "
        f"x[{legend.get_left()[0]:.2f},{legend.get_right()[0]:.2f}] "
        f"y[{legend.get_bottom()[1]:.2f},{legend.get_top()[1]:.2f}]"
    )


@pytest.mark.parametrize("width,height", RESOLUTIONS)
@pytest.mark.parametrize("name,params,captions", STORYBOARDS, ids=[s[0] for s in STORYBOARDS])
def test_the_placed_legend_stays_inside_the_safe_area(width, height, name, params, captions):
    """Choosing another corner must not push the legend out of the frame."""
    comp = Graph()
    with resolution(width, height):
        play_component(
            comp, Graph.Params(**params), width, height, caption=_caption(captions)
        )

    legend = getattr(comp, "last_legend", None)
    assert legend is not None
    left, right, bottom, top = _safe_box(width, height)
    assert legend.get_left()[0] >= left - 1e-6, (
        f"{name}: the legend starts at x={legend.get_left()[0]:.3f}, outside "
        f"the safe area x={left:.3f}"
    )
    assert legend.get_right()[0] <= right + 1e-6
    assert legend.get_bottom()[1] >= bottom - 1e-6
    assert legend.get_top()[1] <= top + 1e-6


@pytest.mark.parametrize("width,height", RESOLUTIONS)
@pytest.mark.parametrize("name,params,captions", STORYBOARDS, ids=[s[0] for s in STORYBOARDS])
def test_the_legend_rows_share_one_text_size_on_one_baseline(width, height, name, params, captions):
    """Every entry has the same size, and its swatch is centred on its label.

    The rows were aligned edge-to-top, so the short colour stroke sat on the
    first line of the label instead of on its middle.
    """
    comp = Graph()
    with resolution(width, height):
        play_component(
            comp, Graph.Params(**params), width, height, caption=_caption(captions)
        )

    legend = getattr(comp, "last_legend", None)
    assert legend is not None
    rows = [m for m in legend.submobjects if m.__class__.__name__ == "VGroup"]
    assert len(rows) == 2, f"{name}: the legend has {len(rows)} rows, not 2"
    for row in rows:
        swatch, label = row.submobjects[0], row.submobjects[1]
        assert swatch.get_center()[1] == pytest.approx(label.get_center()[1], abs=0.05), (
            f"{name}: the swatch is at y={swatch.get_center()[1]:.3f}, the label's "
            f"middle is y={label.get_center()[1]:.3f}"
        )
        assert label.font_size == pytest.approx(MIN_FONT_SIZE, abs=0.5), (
            f"{name}: one entry is set at {label.font_size}, another at {MIN_FONT_SIZE}"
        )

# ---------------------------------------------------------------------------
# LaTeX: a curve named by an expression is set in math, not in source code
# ---------------------------------------------------------------------------


def test_python_expressions_are_typeset_as_latex():
    """The legend must not print Python source: ``x**2`` becomes x squared."""
    assert latex_expression("1 + x + x**2/2") == "1 + x + x^{2}/2"
    assert latex_expression("exp(x)") == "e^{x}"
    assert latex_expression("sin(x) + sqrt(x)") == "\\sin(x) + \\sqrt{x}"
    assert latex_expression("2*x - 1") == "2 \\cdot x - 1"


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_the_legend_typesets_math_labels(width, height):
    """A curve named by its expression is named in LaTeX, like the title."""
    comp = Graph()
    with resolution(width, height):
        play_component(comp, Graph.Params(**TAYLOR), width, height)

    entries = [
        t for t in comp.last_legend.get_family()
        if t.__class__.__name__ == "MathTex"
    ]
    assert entries, "the curves are named by expressions but the legend is plain text"
    assert any("e^{x}" in e.tex_string for e in entries), [e.tex_string for e in entries]
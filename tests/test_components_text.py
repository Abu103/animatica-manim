import pytest
from pathlib import Path
from pydantic import ValidationError

from animatica.components.equation import Equation
from animatica.components.steps_list import StepsList
from animatica.components.title_card import TitleCard
from geometry import (
    RESOLUTIONS,
    assert_beat_timing,
    assert_inside_safe_area,
    assert_no_text_overlap,
    play_component,
)


def test_durations_follow_formulas():
    assert TitleCard().duration(TitleCard.Params(title="T")) == 3.0
    eq = Equation()
    assert eq.duration(Equation.Params(latex=["a"])) == 2.0
    assert eq.duration(Equation.Params(latex=["a", "b", "c"])) == 6.0
    sl = StepsList()
    assert sl.duration(StepsList.Params(items=["a", "b"])) == 4.0
    assert sl.duration(StepsList.Params(items=["a"] * 8)) == 13.0


def test_equation_rejects_unsafe_latex():
    with pytest.raises(ValidationError):
        Equation.Params(latex=[r"\write18{rm -rf}"])


def test_equation_rejects_empty_and_too_many():
    with pytest.raises(ValidationError):
        Equation.Params(latex=[])
    with pytest.raises(ValidationError):
        Equation.Params(latex=["a"] * 7)


def test_steps_and_title_limits():
    with pytest.raises(ValidationError):
        StepsList.Params(items=[])
    with pytest.raises(ValidationError):
        StepsList.Params(items=["a"] * 9)
    with pytest.raises(ValidationError):
        TitleCard.Params(title="x" * 301)


def test_fallback_text():
    assert "Hello" in TitleCard().fallback_text(TitleCard.Params(title="Hello"))
    assert "a^2" in Equation().fallback_text(Equation.Params(latex=["a^2"]))
    assert "one" in StepsList().fallback_text(StepsList.Params(items=["one", "two"]))


@pytest.mark.render
def test_title_card_plays(run_component):
    s, warnings = run_component(TitleCard(), TitleCard.Params(title="Hello", subtitle="World"))
    assert s.renderer.num_plays >= 1 and warnings == []


@pytest.mark.render
@pytest.mark.parametrize("mode", ["reveal", "transform"])
def test_equation_plays(run_component, mode):
    s, warnings = run_component(Equation(), Equation.Params(mode=mode, latex=["a^2+b^2=c^2", "c=\\sqrt{a^2+b^2}"]))
    assert s.renderer.num_plays >= 1 and warnings == []


@pytest.mark.render
def test_equation_bad_latex_degrades_with_warning(run_component):
    s, warnings = run_component(Equation(), Equation.Params(latex=[r"\frac{a}{"]))
    assert s.renderer.num_plays >= 1
    assert len(warnings) == 1 and "equation" in warnings[0]


@pytest.mark.render
def test_steps_list_plays(run_component):
    s, warnings = run_component(StepsList(), StepsList.Params(items=["First", "Second", "Third"]))
    assert s.renderer.num_plays >= 1 and warnings == []


def test_wrap_keeps_explicit_line_breaks():
    from animatica.components._draw import wrap
    assert wrap("F_0 = 0\nF_1 = 1", 40) == "F_0 = 0\nF_1 = 1"
    assert wrap("a " * 30, 20).count("\n") >= 2


# ---------------------------------------------------------------------------
# Equation safe-area regression test
# ---------------------------------------------------------------------------

@pytest.mark.render
def test_equation_no_side_safe_area_warnings(tmp_path):
    """Equation content stays within the 5% side safe-area margins.

    Renders the pythagoras gallery storyboard (equation scene) and checks
    rendered frames at key timestamps to verify no non-background pixels
    appear in the left/right 5% margin band.
    Regression test for fit() upscaling equations to fill the frame width.
    """
    from animatica.pipeline import make_video
    import av
    import numpy as np
    from PIL import Image

    sb_path = tmp_path / "pythagoras_storyboard.json"
    import shutil

    gallery = Path(__file__).resolve().parent.parent / "acceptance/gallery/pythagoras/storyboard.json"
    assert gallery.is_file(), f"missing gallery storyboard: {gallery}"
    shutil.copy(gallery, sb_path)

    result = make_video(
        storyboard_path=sb_path,
        out_dir=tmp_path / "out",
        preview=True,
    )
    assert result.video.is_file(), f"video not produced: {result.video}"

    container = av.open(str(result.video))
    try:
        video_stream = next(s for s in container.streams if s.type == "video")
        width = video_stream.width
        margin_x = int(width * 0.05)  # 5% side margin

        margin_violations = 0
        for frame in container.decode(video_stream):
            ts = float(frame.time) if frame.time is not None else 0
            # Only check equation scene (scene 1: t >= 3.0s)
            if ts < 3.0:
                continue
            rgb = frame.to_ndarray(format="rgb24")
            gray = np.array(Image.fromarray(rgb).convert("L"))
            # Background is dark-blue ~ #0B0B12 (11)
            non_bg = np.abs(gray.astype(int) - 11) > 25
            # Check left and right 5% margin bands
            left_band = non_bg[:, :margin_x]
            right_band = non_bg[:, -margin_x:]
            margin_violations += int(left_band.sum() + right_band.sum())
    finally:
        container.close()

    assert margin_violations == 0, (
        f"equation scene has {margin_violations} non-background pixels "
        f"inside the left/right 5% side safe-area margin"
    )


# ---------------------------------------------------------------------------
# B4: the title card has to fit the frame, keep its text apart and fit its clock
# ---------------------------------------------------------------------------


def _title_card_params() -> TitleCard.Params:
    """The parameters of the conformance storyboard, tests/conformance/title_card.json."""
    return TitleCard.Params(title="Conformance")


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_title_card_content_stays_inside_the_safe_area(width, height):
    """The title must stay inside the safe-area margin.

    It was scaled up to fill the frame, which stretched it over the edges
    of the frame and into the margin frame-lint keeps free.
    """
    beat = play_component(TitleCard(), _title_card_params(), width, height)

    assert_inside_safe_area(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_title_card_text_does_not_overlap(width, height):
    """The title and the subtitle must not land on each other."""
    beat = play_component(TitleCard(), _title_card_params(), width, height)

    assert_no_text_overlap(beat)


@pytest.mark.parametrize("width,height", RESOLUTIONS)
def test_title_card_beat_fits_its_declared_duration(width, height):
    """The animations must fit inside the duration the component declared."""
    beat = play_component(TitleCard(), _title_card_params(), width, height)

    assert_beat_timing(beat)

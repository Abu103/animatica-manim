import pytest
from pydantic import ValidationError

from animatica.components.equation import Equation
from animatica.components.steps_list import StepsList
from animatica.components.title_card import TitleCard


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
    shutil.copy("acceptance/gallery/pythagoras/storyboard.json", sb_path)

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


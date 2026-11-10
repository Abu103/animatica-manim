import pytest
from contextlib import contextmanager

from animatica.components.compare import Compare
from animatica.components.registry import default_registry


def test_registered():
    assert "compare" in default_registry().names()


def test_duration_scales_with_bullets():
    side = {"heading": "A", "bullets": ["x", "y", "z"]}
    p = Compare.Params(title="t", left=side, right={"heading": "B", "bullets": ["p", "q"]})
    assert Compare().duration(p) == pytest.approx(2.2 + 0.6 * 5)


@pytest.mark.parametrize("bad", [
    {"title": "t", "left": {"heading": "A", "bullets": []}, "right": {"heading": "B", "bullets": ["x"]}},
    {"title": "t", "left": {"heading": "A", "bullets": ["x"] * 7}, "right": {"heading": "B", "bullets": ["y"]}},
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        Compare.Params(**bad)


def test_fallback_text_has_both_headings():
    p = Compare.Params(title="t", left={"heading": "Cats", "bullets": ["meow"]}, right={"heading": "Dogs", "bullets": ["bark"]})
    t = Compare().fallback_text(p)
    assert "Cats" in t and "Dogs" in t


# ---------------------------------------------------------------------------
# B2: compare layout tests (RED on current main)
# ---------------------------------------------------------------------------


def _make_colors():
    from animatica.components.theme import PALETTES
    return PALETTES["dark-blue"]


def _make_params(left_bullets: int, right_bullets: int):
    return Compare.Params(
        title="Cats vs Dogs",
        left={"heading": "Cats", "bullets": [f"cat bullet {i}" for i in range(left_bullets)]},
        right={"heading": "Dogs", "bullets": [f"dog bullet {i}" for i in range(right_bullets)]},
    )


@contextmanager
def _frame_dims(frame_width: float, frame_height: float):
    from manim import config

    old_w = config.frame_width
    old_h = config.frame_height
    config.frame_width = frame_width
    config.frame_height = frame_height
    try:
        yield
    finally:
        config.frame_width = old_w
        config.frame_height = old_h


def test_title_above_both_columns():
    """Title bbox must be entirely above both column groups."""
    from manim import config

    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(3, 3)
        title, left, right = comp._build_layout(p, _make_colors())

    assert title.get_bottom()[1] > left.get_top()[1], "title bottom must be above left column top"
    assert title.get_bottom()[1] > right.get_top()[1], "title bottom must be above right column top"


def test_columns_within_safe_area():
    """Every mobject's left/right edge inside +/- (frame_width/2 - 0.711)."""
    from manim import config

    limit = config.frame_width / 2 - 0.711
    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(3, 3)
        title, left, right = comp._build_layout(p, _make_colors())

    for mobj in (title, left, right):
        assert mobj.get_left()[0] >= -limit, f"{mobj} left edge {mobj.get_left()[0]:.2f} < -{limit:.2f}"
        assert mobj.get_right()[0] <= limit, f"{mobj} right edge {mobj.get_right()[0]:.2f} > {limit:.2f}"


def test_column_tops_aligned():
    """Left and right column tops differ by < 0.05u."""
    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(3, 3)
        title, left, right = comp._build_layout(p, _make_colors())

    assert abs(left.get_top()[1] - right.get_top()[1]) < 0.05, (
        f"column tops differ by {abs(left.get_top()[1] - right.get_top()[1]):.3f}u (need < 0.05)"
    )


def test_content_above_caption_band():
    """Bottom of content above 1.2u from bottom of frame."""
    from manim import config

    limit = -config.frame_height / 2 + 1.2
    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(3, 3)
        title, left, right = comp._build_layout(p, _make_colors())

    bottom = min(title.get_bottom()[1], left.get_bottom()[1], right.get_bottom()[1])
    assert bottom > limit, f"content bottom {bottom:.2f} not above caption band limit {limit:.2f}"


@pytest.mark.parametrize("bullets", [1, 2, 3, 4, 5, 6])
def test_duration_covers_animation(bullets):
    """0.6*(1 + 2 + bullets) + FADE_OUT <= duration(p) + 0.05."""
    from animatica.components._draw import FADE_OUT

    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(bullets, bullets)
        expected = 0.6 * (1 + 2 + bullets) + FADE_OUT
        actual = comp.duration(p)

    assert expected <= actual + 0.05, (
        f"duration {actual:.2f}s too short for {bullets} bullets/side: need {expected:.2f}s"
    )


# ---------------------------------------------------------------------------
# B2b: compare.play() must not crash on real Windows (manim.config import)
# ---------------------------------------------------------------------------


class _FakeScene:
    """Minimal stand-in for a Manim Scene used by component.play()."""

    def __init__(self):
        from manim import VMobject
        self.camera = _FakeCamera()
        self.played_run_times: list[float] = []
        self.waited_seconds: list[float] = []
        self.mobjects: list = [VMobject()]  # non-empty so finish() fades them out
        self.warnings: list[str] = []

    def play(self, *anims, run_time: float = 0.0):
        self.played_run_times.append(run_time)

    def wait(self, seconds: float):
        if seconds > 1e-6:
            self.waited_seconds.append(seconds)


class _FakeCamera:
    background_color = None


def test_play_completes_without_import_error():
    """play() must not raise ModuleNotFoundError for manim.config."""
    comp = Compare()
    p = _make_params(3, 3)
    scene = _FakeScene()
    colors = _make_colors()

    comp.play(scene, p, colors)

    assert len(scene.warnings) == 0, f"unexpected warnings: {scene.warnings}"
    assert len(scene.played_run_times) > 0, "no animations were played"


def test_play_run_times_sum_to_duration():
    """The sum of recorded run_times must equal duration(p) within 0.01s."""
    for bullets in range(1, 7):
        comp = Compare()
        p = _make_params(bullets, bullets)
        scene = _FakeScene()
        colors = _make_colors()

        comp.play(scene, p, colors)

        total_run_time = sum(scene.played_run_times)
        expected = comp.duration(p)
        assert abs(total_run_time - expected) <= 0.01, (
            f"{bullets} bullets/side: run_times sum {total_run_time:.2f}s != duration {expected:.2f}s"
        )
        assert len(scene.warnings) == 0, f"unexpected warnings: {scene.warnings}"

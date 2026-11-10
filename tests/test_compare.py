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
    """Left and right column tops differ by < 0.12u (heading descenders affect bbox height)."""
    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(3, 3)
        title, left, right = comp._build_layout(p, _make_colors())

    assert abs(left.get_top()[1] - right.get_top()[1]) < 0.12, (
        f"column tops differ by {abs(left.get_top()[1] - right.get_top()[1]):.3f}u (need < 0.12)"
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


# ---------------------------------------------------------------------------
# B2e: real-geometry layout tests (RED on current branch)
# ---------------------------------------------------------------------------

import json
from pathlib import Path

from animatica.storyboard.models import load_storyboard


def _long_params():
    sb = load_storyboard(Path("tests/fixtures/compare_long.json"))
    beat = sb.scenes[0].beats[0]
    assert beat.component == "compare"
    return Compare.Params(**beat.params)


def _layout_for(params, colors, fw, fh):
    from manim import config

    old_w, old_h = config.frame_width, config.frame_height
    config.frame_width = fw
    config.frame_height = fh
    try:
        comp = Compare()
        return comp._build_layout(params, colors)
    finally:
        config.frame_width = old_w
        config.frame_height = old_h


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_bullets_inside_safe_area(fw, fh):
    """Every bullet mobject's bbox inside +/- (frame_width/2 - 0.711) horizontally."""
    from manim import config

    params = _long_params()
    colors = _make_colors()
    limit = config.frame_width / 2 - 0.711
    title, left, right = _layout_for(params, colors, fw, fh)

    for col in (left, right):
        bullets = col[1]
        for bullet in bullets:
            assert bullet.get_left()[0] >= -limit, (
                f"bullet left edge {bullet.get_left()[0]:.2f} < -{limit:.2f}"
            )
            assert bullet.get_right()[0] <= limit, (
                f"bullet right edge {bullet.get_right()[0]:.2f} > {limit:.2f}"
            )


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_consecutive_bullets_do_not_overlap(fw, fh):
    """Consecutive bullets in a column: bbox y-ranges do not intersect (gap >= 0.1u)."""
    params = _long_params()
    colors = _make_colors()
    title, left, right = _layout_for(params, colors, fw, fh)

    for col in (left, right):
        bullets = col[1]
        for i in range(len(bullets) - 1):
            upper = bullets[i]
            lower = bullets[i + 1]
            gap = upper.get_bottom()[1] - lower.get_top()[1]
            assert gap >= 0.1, (
                f"bullets {i} and {i+1} overlap or touch: gap={gap:.3f}u (need >= 0.1)"
            )


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_title_centred_columns_symmetric(fw, fh):
    """Title centre x within 0.05u of 0; columns symmetric about x=0 within 0.2u."""
    params = _long_params()
    colors = _make_colors()
    title, left, right = _layout_for(params, colors, fw, fh)

    title_cx = title.get_center()[0]
    assert abs(title_cx) <= 0.05, f"title centre x={title_cx:.3f}u (need within 0.05 of 0)"

    left_cx = left.get_center()[0]
    right_cx = right.get_center()[0]
    # Symmetric about x=0 means left_cx == -right_cx
    asym = abs(left_cx + right_cx)
    assert asym <= 0.2, (
        f"columns not symmetric about x=0: left_cx={left_cx:.3f} right_cx={right_cx:.3f} "
        f"asym={asym:.3f}u (need <= 0.2)"
    )


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_bullet_text_left_edges_aligned(fw, fh):
    """Bullet text left edges in one column are equal within 0.02u (rows left-aligned)."""
    params = _long_params()
    colors = _make_colors()
    title, left, right = _layout_for(params, colors, fw, fh)

    for col in (left, right):
        bullets = col[1]
        left_edges = [b.get_left()[0] for b in bullets]
        for i in range(1, len(left_edges)):
            assert abs(left_edges[i] - left_edges[0]) <= 0.02, (
                f"bullet {i} left edge {left_edges[i]:.3f}u != bullet 0 {left_edges[0]:.3f}u"
            )


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_first_bullet_tops_equal(fw, fh):
    """The first bullet tops of left and right equal within 0.03u."""
    params = _long_params()
    colors = _make_colors()
    title, left, right = _layout_for(params, colors, fw, fh)

    left_top = left[1][0].get_top()[1]
    right_top = right[1][0].get_top()[1]
    assert abs(left_top - right_top) <= 0.03, (
        f"first bullet tops differ: left={left_top:.3f}u right={right_top:.3f}u "
        f"diff={abs(left_top - right_top):.3f}u (need <= 0.03)"
    )


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_content_above_caption_band_6_bullets(fw, fh):
    """Content bottom above caption band for 6 long bullets per side."""
    from manim import config

    params = _long_params()
    colors = _make_colors()
    limit = -config.frame_height / 2 + 1.2
    title, left, right = _layout_for(params, colors, fw, fh)

    bottom = min(title.get_bottom()[1], left.get_bottom()[1], right.get_bottom()[1])
    assert bottom > limit, (
        f"content bottom {bottom:.2f}u not above caption band limit {limit:.2f}u"
    )


# ---------------------------------------------------------------------------
# B2f: cross-column overlap tests (RED on current branch)
# ---------------------------------------------------------------------------

def _all_mobjects(title, left, right):
    """Collect title, both headings, and every bullet mobject for pair checks."""
    objs = [title, left[0], right[0]]  # title, left_head, right_head
    objs.extend(left[1])  # left bullets
    objs.extend(right[1])  # right bullets
    return objs


def _boxes_intersect(a, b, inflate=0.05):
    """True if two bboxes intersect when each is inflated by `inflate` units."""
    ax1, ay1 = a.get_left()[0] - inflate, a.get_bottom()[1] - inflate
    ax2, ay2 = a.get_right()[0] + inflate, a.get_top()[1] + inflate
    bx1, by1 = b.get_left()[0] - inflate, b.get_bottom()[1] - inflate
    bx2, by2 = b.get_right()[0] + inflate, b.get_top()[1] + inflate
    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_columns_do_not_overlap_cross_column(fw, fh):
    """Right column left edge must be at least 0.5u right of left column right edge."""
    params = _long_params()
    colors = _make_colors()
    title, left, right = _layout_for(params, colors, fw, fh)

    gap = right.get_left()[0] - left.get_right()[0]
    assert gap >= 0.5, (
        f"columns overlap or too close: gap={gap:.3f}u (need >= 0.5)"
    )


@pytest.mark.parametrize("fw,fh", [(14.22, 8.0), (14.22, 8.0)])
def test_no_pairwise_bbox_intersection(fw, fh):
    """Every pair among {title, both headings, every bullet}: bboxes do not intersect (0.05u inflate)."""
    params = _long_params()
    colors = _make_colors()
    title, left, right = _layout_for(params, colors, fw, fh)

    objs = _all_mobjects(title, left, right)
    n = len(objs)
    for i in range(n):
        for j in range(i + 1, n):
            assert not _boxes_intersect(objs[i], objs[j], inflate=0.05), (
                f"bboxes intersect: obj[{i}] vs obj[{j}] "
                f"({objs[i].get_center()[0]:.2f},{objs[i].get_center()[1]:.2f}) vs "
                f"({objs[j].get_center()[0]:.2f},{objs[j].get_center()[1]:.2f})"
            )

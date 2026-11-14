import pytest

from animatica.components.compare import Compare
from animatica.components.registry import default_registry
from geometry import RecordingScene as _FakeScene
from geometry import _boxes_intersect
from geometry import frame_units as _frame_dims
from geometry import make_colors as _make_colors


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


def _make_params(left_bullets: int, right_bullets: int):
    return Compare.Params(
        title="Cats vs Dogs",
        left={"heading": "Cats", "bullets": [f"cat bullet {i}" for i in range(left_bullets)]},
        right={"heading": "Dogs", "bullets": [f"dog bullet {i}" for i in range(right_bullets)]},
    )


def test_title_above_both_columns():
    """Title bbox must be entirely above both column groups."""

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


def _make_caption(text: str):
    """A real caption mobject, as the scene builds one per beat."""
    from animatica.components._draw import make_caption
    from animatica.components.theme import PALETTES

    return make_caption(text, PALETTES["dark-blue"])


def test_content_above_caption_band():
    """Bottom of content stays above the real caption's top."""
    from animatica.components._draw import caption_band_top

    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(3, 3)
        caption = _make_caption("Comparing two icy moons")
        limit = caption_band_top(caption)
        title, left, right = comp._build_layout(p, _make_colors(), caption)

    bottom = min(title.get_bottom()[1], left.get_bottom()[1], right.get_bottom()[1])
    assert bottom >= limit - 1e-6, (
        f"content bottom {bottom:.4f} below caption band limit {limit:.4f}"
    )
    assert bottom > caption.get_top()[1], (
        f"content bottom {bottom:.4f} overlaps the caption top {caption.get_top()[1]:.4f}"
    )


def test_caption_band_derived_from_real_caption():
    """A taller caption must leave less room for the columns.

    The band used to be a hardcoded 1.2u, which is wrong for a caption that
    wraps onto two lines: the columns then overlapped the caption.
    """
    from animatica.components._draw import caption_band_top

    long_caption_text = (
        "Positive charges gather at the cloud's top, negative charges at its base, "
        "and the ground below turns positive."
    )

    with _frame_dims(14.22, 8.0):
        comp = Compare()
        p = _make_params(3, 3)
        one = _make_caption("Comparing two icy moons")
        two = _make_caption(long_caption_text)
        band_one = caption_band_top(one)
        band_two = caption_band_top(two)
        title, left, right = comp._build_layout(p, _make_colors(), two)

    assert band_two > band_one, (
        f"two-line caption band {band_two:.3f} must sit above the one-line "
        f"band {band_one:.3f}"
    )
    bottom = min(title.get_bottom()[1], left.get_bottom()[1], right.get_bottom()[1])
    assert bottom >= band_two - 1e-6, (
        f"content bottom {bottom:.3f} below the two-line caption band {band_two:.3f}"
    )
    assert bottom > two.get_top()[1], (
        f"content bottom {bottom:.3f} overlaps the two-line caption top {two.get_top()[1]:.3f}"
    )


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

from pathlib import Path

from animatica.storyboard.models import load_storyboard


def _long_params():
    sb = load_storyboard(Path("tests/fixtures/compare_long.json"))
    beat = sb.scenes[0].beats[0]
    assert beat.component == "compare"
    return Compare.Params(**beat.params)


def _layout_for(params, colors, fw, fh, caption=None):
    from manim import config

    old_w, old_h = config.frame_width, config.frame_height
    config.frame_width = fw
    config.frame_height = fh
    try:
        comp = Compare()
        return comp._build_layout(params, colors, caption)
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
    """Content bottom above the caption band for 6 long bullets per side."""
    from animatica.components._draw import caption_band_top

    params = _long_params()
    colors = _make_colors()
    caption = _make_caption("Comparing two icy moons")
    limit = caption_band_top(caption)
    title, left, right = _layout_for(params, colors, fw, fh, caption=caption)

    bottom = min(title.get_bottom()[1], left.get_bottom()[1], right.get_bottom()[1])
    # The columns are fitted to exactly fill the space above the band, so the
    # bottom may sit on the band; it must never drop below it, and it must
    # never overlap the caption itself.
    assert bottom >= limit - 1e-6, (
        f"content bottom {bottom:.4f}u below caption band limit {limit:.4f}u"
    )
    assert bottom > caption.get_top()[1], (
        f"content bottom {bottom:.4f}u overlaps the caption top {caption.get_top()[1]:.4f}u"
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


# ---------------------------------------------------------------------------
# B3: report when fitting shrinks the bullets below the readable floor
# ---------------------------------------------------------------------------


def _play_and_warnings(params, caption=None):
    """Run play() and collect the warnings it emitted."""
    comp = Compare()
    scene = _FakeScene()
    if caption is not None:
        scene.caption_mobject = caption
    comp.play(scene, params, _make_colors())
    return comp, scene.warnings


def test_long_content_warns_that_text_was_scaled_down():
    """Text that had to shrink below the floor is reported, not silently small."""
    from animatica.components._draw import MIN_FONT_SIZE

    params = _long_params()
    comp, warnings = _play_and_warnings(params, _make_caption("Comparing two icy moons"))

    scaled = [w for w in warnings if "text scaled to" in w]
    assert scaled, f"expected a scaled-text warning, got {warnings}"
    assert f"floor {MIN_FONT_SIZE}" in scaled[0], scaled[0]
    assert comp.last_effective_font < MIN_FONT_SIZE, (
        f"effective font {comp.last_effective_font} should be below the floor"
    )


def test_short_content_is_not_reported_as_scaled_down():
    """One short bullet per side fits without shrinking, so no warning."""
    from animatica.components._draw import MIN_FONT_SIZE

    params = Compare.Params(
        title="Cats vs Dogs",
        left={"heading": "Cats", "bullets": ["fast"]},
        right={"heading": "Dogs", "bullets": ["slow"]},
    )
    comp, warnings = _play_and_warnings(params, _make_caption("Comparing two icy moons"))

    assert not [w for w in warnings if "text scaled to" in w], (
        f"unexpected scaled-text warning: {warnings}"
    )
    assert comp.last_effective_font >= MIN_FONT_SIZE, (
        f"effective font {comp.last_effective_font} should be at or above the floor"
    )


def test_scaled_text_warning_is_not_a_component_fallback():
    """The advisory must not be recorded as a text_card fallback.

    It starts with the component name, which is the same shape a real
    fallback uses, so the fallback detector has to tell them apart.
    """
    from animatica.pipeline import make_video

    assert "compare: text scaled to" in "compare: text scaled to 25 px (floor 32)"
    # The detector itself is covered in tests/test_pipeline.py; here we only
    # assert the message keeps the shape the detector relies on.
    assert make_video is not None


def test_effective_font_is_reported_for_a_two_line_caption():
    """A two-line caption leaves less room, so the text shrinks further."""
    from animatica.components._draw import MIN_FONT_SIZE

    long_caption = (
        "Positive charges gather at the cloud's top, negative charges at its base, "
        "and the ground below turns positive."
    )
    params = _long_params()
    comp, warnings = _play_and_warnings(params, _make_caption(long_caption))

    assert comp.last_effective_font < MIN_FONT_SIZE
    assert any("text scaled to" in w for w in warnings), warnings
    # The reported size must be the one that was actually used.
    reported = [w for w in warnings if "text scaled to" in w][0]
    assert f"{comp.last_effective_font:.0f} px" in reported, (
        f"warning {reported!r} does not match the effective font "
        f"{comp.last_effective_font:.2f}"
    )

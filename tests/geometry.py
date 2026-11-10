"""Shared geometry helpers for the component layout tests.

Every component has to satisfy the same three rules, and the rules are
checked against real mobjects rather than against the source:

  1. its content stays inside the safe-area margin frame-lint keeps free;
  2. no two pieces of text overlap;
  3. the beat's animations fit inside the duration the component declared,
     so the captions do not drift.

These helpers used to live in ``tests/test_compare.py``. They are shared
now so the next component does not copy them.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

#: The pixel resolutions the layout tests check. Manim always uses a frame
#: height of 8.0 units, so 16:9 at either resolution has the same geometry
#: in units -- what differs is how many pixels the content covers, which is
#: what frame-lint measures.
RESOLUTIONS = [(1280, 720), (1920, 1080)]

#: frame-lint keeps this fraction of each frame edge free of content.
SAFE_AREA_MARGIN = 0.05

#: Manim's frame height in units, whatever the pixel resolution.
FRAME_HEIGHT = 8.0

#: Mobject classes that carry text. Decorative shapes (lines, rectangles,
#: dots) may cross text without anything being unreadable.
TEXT_CLASSES = ("Text", "MarkupText", "MathTex", "Tex", "Paragraph", "Code", "SVGText", "CodeBlock")


@contextmanager
def frame_units(frame_width: float, frame_height: float):
    """Set Manim's frame geometry, in units."""
    from manim import config

    old_w, old_h = config.frame_width, config.frame_height
    config.frame_width = frame_width
    config.frame_height = frame_height
    try:
        yield
    finally:
        config.frame_width, config.frame_height = old_w, old_h


@contextmanager
def resolution(pixel_width: int, pixel_height: int):
    """Set Manim's frame geometry to the one a pixel resolution implies.

    Manim always uses a frame height of 8.0 units, so 16:9 at 1280x720 and
    at 1920x1080 has the same geometry in units; what differs is how many
    pixels the content covers, which is what frame-lint measures.
    """
    from manim import config

    old = (config.pixel_width, config.pixel_height, config.frame_width, config.frame_height)
    config.pixel_width = pixel_width
    config.pixel_height = pixel_height
    config.frame_height = FRAME_HEIGHT
    config.frame_width = FRAME_HEIGHT * pixel_width / pixel_height
    try:
        yield
    finally:
        (config.pixel_width, config.pixel_height, config.frame_width, config.frame_height) = old


def make_colors(name: str = "dark-blue"):
    from animatica.components.theme import PALETTES

    return PALETTES[name]


class _FakeCamera:
    background_color = None


class RecordingScene:
    """A minimal stand-in for a Manim Scene that records what play() did.

    Components only need a camera, ``play``/``wait``/``add``/``remove`` and
    a ``warnings`` list; recording the calls is what lets a test check the
    timing and the geometry without rendering a video.
    """

    def __init__(self):
        from manim import VMobject

        self.camera = _FakeCamera()
        self.played_run_times: list[float] = []
        self.waited_seconds: list[float] = []
        self.animations: list = []
        self.mobjects: list = [VMobject()]  # non-empty so finish() fades them out
        self.warnings: list[str] = []

    def play(self, *anims, run_time: float = 0.0):
        self.played_run_times.append(run_time)
        self.animations.extend(anims)

    def wait(self, seconds: float):
        if seconds > 1e-6:
            self.waited_seconds.append(seconds)

    def add(self, *mobs):
        self.mobjects.extend(mobs)

    def remove(self, *mobs):
        for m in mobs:
            if m in self.mobjects:
                self.mobjects.remove(m)


@dataclass
class Beat:
    """What one component's play() did, and the geometry it produced."""

    scene: RecordingScene
    mobjects: list = field(default_factory=list)
    texts: list = field(default_factory=list)
    frame_width: float = 0.0
    frame_height: float = 0.0
    duration: float = 0.0
    label: str = ""


def _is_text(mobject: Any) -> bool:
    return mobject.__class__.__name__ in TEXT_CLASSES


def _texts_of(mobject: Any) -> list:
    """The text elements of a mobject.

    A group carries its text in submobjects, so the group is expanded to
    find them; a text mobject is its own element.
    """
    if _is_text(mobject):
        return [mobject]
    out: list = []
    for sub in getattr(mobject, "submobjects", None) or []:
        out.extend(_texts_of(sub))
    return out


def _distinct(mobjects: list) -> list:
    """Drop copies of the same element.

    ``mobject.animate`` builds a copy, so a mobject that is animated in
    place shows up twice in the animation list. Two texts with the same
    content and the same bounding box are the same visible element.
    """
    seen: set = set()
    out = []
    for m in mobjects:
        try:
            content = m.text
        except Exception:
            content = ""
        key = (
            content,
            round(m.get_left()[0], 2),
            round(m.get_right()[0], 2),
            round(m.get_bottom()[1], 2),
            round(m.get_top()[1], 2),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def play_component(
    component,
    params,
    pixel_width: int,
    pixel_height: int,
    colors=None,
    label: str = "",
) -> Beat:
    """Run ``component.play()`` at a pixel resolution and collect the result."""
    colors = colors or make_colors()
    with resolution(pixel_width, pixel_height):
        from manim import config

        scene = RecordingScene()
        component.play(scene, params, colors)

        mobjects = []
        for anim in scene.animations:
            mob = getattr(anim, "mobject", None)
            if mob is None:
                continue
            if isinstance(mob, (list, tuple)):
                mobjects.extend(mob)
            else:
                mobjects.append(mob)

        texts = _distinct([t for m in mobjects for t in _texts_of(m)])
        return Beat(
            scene=scene,
            mobjects=mobjects,
            texts=texts,
            frame_width=config.frame_width,
            frame_height=config.frame_height,
            duration=component.duration(params),
            label=label or getattr(component, "name", ""),
        )


def assert_inside_safe_area(beat: Beat) -> None:
    """No content may reach into the safe-area margin."""
    margin_x = beat.frame_width * SAFE_AREA_MARGIN
    margin_y = beat.frame_height * SAFE_AREA_MARGIN
    left, right = -beat.frame_width / 2 + margin_x, beat.frame_width / 2 - margin_x
    bottom, top = -beat.frame_height / 2 + margin_y, beat.frame_height / 2 - margin_y

    for mob in beat.mobjects:
        if mob.width == 0 and mob.height == 0:
            continue
        l, r = mob.get_left()[0], mob.get_right()[0]
        b, t = mob.get_bottom()[1], mob.get_top()[1]
        assert l >= left - 1e-6 and r <= right + 1e-6, (
            f"{beat.label}: {mob.__class__.__name__} spans x[{l:.3f},{r:.3f}], "
            f"outside the safe area x[{left:.3f},{right:.3f}]"
        )
        assert b >= bottom - 1e-6 and t <= top + 1e-6, (
            f"{beat.label}: {mob.__class__.__name__} spans y[{b:.3f},{t:.3f}], "
            f"outside the safe area y[{bottom:.3f},{top:.3f}]"
        )


def _boxes_intersect(a, b, inflate: float = 0.05) -> bool:
    ax1, ay1 = a.get_left()[0] - inflate, a.get_bottom()[1] - inflate
    ax2, ay2 = a.get_right()[0] + inflate, a.get_top()[1] + inflate
    bx1, by1 = b.get_left()[0] - inflate, b.get_bottom()[1] - inflate
    bx2, by2 = b.get_right()[0] + inflate, b.get_top()[1] + inflate
    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)


def assert_no_text_overlap(beat: Beat, inflate: float = 0.05) -> None:
    """No two pieces of text may overlap."""
    texts = beat.texts
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            assert not _boxes_intersect(a, b, inflate), (
                f"{beat.label}: text overlaps -- "
                f"{_describe(a)} vs {_describe(b)}"
            )


def _describe(mob) -> str:
    try:
        content = mob.text
    except Exception:
        content = ""
    return (
        f"{content!r} at x[{mob.get_left()[0]:.2f},{mob.get_right()[0]:.2f}] "
        f"y[{mob.get_bottom()[1]:.2f},{mob.get_top()[1]:.2f}]"
    )


def assert_beat_timing(beat: Beat) -> None:
    """The beat must occupy exactly the duration its component declared.

    ``Clock`` pads a beat with waits so that it fills its budget, so the
    only way the total can differ from the declared duration is an overrun:
    the animations took longer than the beat was allowed to take and the
    captions drift out of sync with the video.
    """
    scene = beat.scene
    animations = sum(scene.played_run_times)
    holds = sum(scene.waited_seconds)

    assert animations <= beat.duration + 0.01, (
        f"{beat.label}: animations run {animations:.3f}s but the beat is only "
        f"{beat.duration:.3f}s long (over by {animations - beat.duration:.3f}s)"
    )
    assert abs(animations + holds - beat.duration) <= 0.01, (
        f"{beat.label}: the beat takes {animations + holds:.3f}s "
        f"(animations {animations:.3f}s + holds {holds:.3f}s) but declares "
        f"{beat.duration:.3f}s"
    )

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
        self.plays: list[tuple[list, float]] = []
        self.mobjects: list = [VMobject()]  # non-empty so finish() fades them out
        self.warnings: list[str] = []

    def play(self, *anims, run_time: float = 0.0):
        self.played_run_times.append(run_time)
        self.animations.extend(anims)
        self.plays.append((list(anims), run_time))

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
    on_screen: dict = field(default_factory=dict)
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


def _collect_animation(anim, out: list) -> None:
    """Collect every mobject an animation touches, nested ones included.

    A ``LaggedStart`` holds its own animations and has an empty mobject of
    its own, so without recursing the bars of a chart would never be
    looked at.
    """
    nested = getattr(anim, "animations", None)
    if nested:
        for sub in nested:
            _collect_animation(sub, out)
    mob = getattr(anim, "mobject", None)
    if mob is None:
        return
    if isinstance(mob, (list, tuple)):
        out.extend(mob)
    else:
        out.append(mob)


def _on_screen(scene: RecordingScene) -> dict:
    """When each mobject is on screen, as (start, end).

    A mobject is on screen from the animation that shows it until the
    animation that hides it. A mobject that fades out while another one
    fades in at the same place is being replaced, not colliding with it.
    """
    from manim import FadeOut

    windows: dict[int, list[float]] = {}
    t = 0.0
    for anims, run_time in scene.plays:
        for anim in anims:
            mob = getattr(anim, "mobject", None)
            if mob is None:
                continue
            if isinstance(anim, FadeOut):
                windows.setdefault(id(mob), [0.0, t])[1] = t
            else:
                windows.setdefault(id(mob), [t, float("inf")])
        t += run_time
    return {key: (value[0], value[1]) for key, value in windows.items()}


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
            _collect_animation(anim, mobjects)

        texts = _distinct([t for m in mobjects for t in _texts_of(m)])
        return Beat(
            scene=scene,
            mobjects=mobjects,
            texts=texts,
            on_screen=_on_screen(scene),
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
    """No two pieces of text may be on screen in the same place."""
    texts = beat.texts
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            if not _boxes_intersect(a, b, inflate):
                continue
            if not _shown_together(beat, a, b):
                continue
            assert False, (
                f"{beat.label}: text overlaps -- "
                f"{_describe(a)} vs {_describe(b)}"
            )


def _shown_together(beat: Beat, a, b) -> bool:
    """True if both texts are on screen at the same time.

    A text that is faded out while the next one fades in at the same place
    is being replaced, not colliding with it.
    """
    wa = beat.on_screen.get(id(a))
    wb = beat.on_screen.get(id(b))
    if wa is None or wb is None:
        return True
    return wa[0] < wb[1] and wb[0] < wa[1]


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


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def _point_near(point, mobject, inflate: float) -> bool:
    """True when the point is inside the mobject's box, grown by `inflate`."""
    left = mobject.get_left()[0] - inflate
    right = mobject.get_right()[0] + inflate
    bottom = mobject.get_bottom()[1] - inflate
    top = mobject.get_top()[1] + inflate
    return left <= point[0] <= right and bottom <= point[1] <= top


def _edges_of(beat: Beat) -> list:
    """The lines a beat drew."""
    from manim import Line

    return [m for m in beat.mobjects if isinstance(m, Line)]


def _label(mobject) -> str:
    try:
        content = mobject.text
    except Exception:
        content = mobject.__class__.__name__
    return f"{content!r} at x[{mobject.get_left()[0]:.2f},{mobject.get_right()[0]:.2f}]"


def assert_edges_connect_parent_and_child(
    beat: Beat,
    pairs: list[tuple],
    edges: list | None = None,
    nodes: list | None = None,
    inflate: float = 0.2,
) -> None:
    """Every edge must run from its parent to its child, and touch no other node.

    ``pairs`` is the list of relations the component is supposed to draw, as
    (parent, child) pairs of mobjects. A component that draws a tree or a
    graph has to build its edges from the real relation; one that guesses the
    children from the depth or from the label draws edges into another
    branch, and the frames look plausible while the picture is wrong.

    Three things have to hold:

    * every edge starts on a node and ends on a node;
    * the node it starts on and the node it ends on are a parent and a child;
    * every relation is drawn once and only once -- an extra edge that runs
      to a node of another branch is a bug even when all the right edges are
      there as well.
    """
    if edges is None:
        edges = _edges_of(beat)
    if nodes is None:
        nodes = []
        for parent, child in pairs:
            for mob in (parent, child):
                if not any(mob is known for known in nodes):
                    nodes.append(mob)

    expected = {(id(parent), id(child)) for parent, child in pairs}
    assert edges, f"{beat.label}: the component drew no edges at all"

    drawn: set[tuple[int, int]] = set()
    for edge in edges:
        start = edge.get_start()
        end = edge.get_end()
        starts = [n for n in nodes if _point_near(start, n, inflate)]
        ends = [n for n in nodes if _point_near(end, n, inflate)]

        assert starts, (
            f"{beat.label}: an edge starts at ({start[0]:.2f},{start[1]:.2f}), "
            "which is not on any node"
        )
        assert ends, (
            f"{beat.label}: an edge ends at ({end[0]:.2f},{end[1]:.2f}), "
            "which is not on any node"
        )

        matched = [
            (s, e) for s in starts for e in ends if (id(s), id(e)) in expected
        ]
        assert matched, (
            f"{beat.label}: an edge connects {_label(starts[0])} to "
            f"{_label(ends[0])}, and that is not a parent and its child"
        )

        parent, child = matched[0]
        foreign = [
            n
            for n in nodes
            if n is not parent
            and n is not child
            and (_point_near(start, n, inflate) or _point_near(end, n, inflate))
        ]
        assert not foreign, (
            f"{beat.label}: an edge from {_label(parent)} to {_label(child)} "
            f"also touches {_label(foreign[0])}, which is neither"
        )
        drawn.add((id(parent), id(child)))

    missing = expected - drawn
    assert not missing, (
        f"{beat.label}: {len(missing)} relation(s) are not drawn at all"
    )
    assert len(drawn) == len(edges), (
        f"{beat.label}: {len(edges)} edges for {len(expected)} relations: "
        "an edge is drawn twice or to a node that is not its child"
    )


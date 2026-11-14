"""Shared Manim helpers for components: timing budget, text fitting, text-card fallback, warnings."""
from __future__ import annotations

import re
import textwrap
from typing import Any

from animatica.components.theme import ThemeColors

MIN_FONT_SIZE = 32  # Manim font_size units; ~3% of 1080p height
FADE_OUT = 0.4


def unescape_code(code: Any) -> Any:
    """Turn a literal backslash-n into a newline when `code` has no real newline.

    Models often double-escape the code string in JSON, so a three-line function
    arrives as one line holding `\\n` twice and every `lines` entry looks out of
    range. Code that already has a real newline is left alone, since a `\\n`
    inside it can be a string literal.
    """
    if isinstance(code, str) and "\n" not in code and "\\n" in code:
        return code.replace("\\r\\n", "\n").replace("\\n", "\n")
    return code


def warn(scene: Any, message: str) -> None:
    sink = getattr(scene, "warnings", None)
    if sink is not None:
        sink.append(message)


def frame_rate() -> float:
    """The frame rate of the video being written (30 when Manim is absent)."""
    try:
        from manim import config

        return float(config.frame_rate)
    except Exception:  # pragma: no cover - manim is not installed
        return 30.0


_FONT_CANDIDATES = ("Segoe UI", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans", "Liberation Sans", "Noto Sans")
_FONT_CACHE: list[str | None] = []


def pick_font() -> str | None:
    """First clean sans-serif installed on this machine (None = leave Manim's default)."""
    if not _FONT_CACHE:
        found = None
        try:
            import manimpango
            available = set(manimpango.list_fonts())
            found = next((f for f in _FONT_CANDIDATES if f in available), None)
        except Exception:
            found = None
        _FONT_CACHE.append(found)
    return _FONT_CACHE[0]


def prepare(scene: Any, colors: ThemeColors) -> None:
    scene.camera.background_color = colors.background
    font = pick_font()
    if font:
        try:
            from manim import MarkupText, Text
            Text.set_default(font=font)
            MarkupText.set_default(font=font)
        except Exception:
            pass  # cosmetic only


def wrap(text: str, width: int) -> str:
    """Wrap each line to `width` characters, keeping the caller's own line breaks."""
    out: list[str] = []
    for line in text.split("\n"):
        out.extend(textwrap.wrap(line, width=width) or [""])
    return "\n".join(out)


#: What marks a piece of text as math rather than prose: a power, a subscript,
#: a backslash command, a division sign next to a word, a Python power, or a
#: function call.
_MATH_HINT = re.compile(
    r"(?<=[A-Za-z0-9])[\\^_\/]|[\\^_\/](?=[A-Za-z0-9])"
    r"|\*\*"
    r"|\b(?:exp|sin|cos|tan|log|ln|sqrt)\s*\("
)

#: Python function names that have a LaTeX command of the same name.
_FUNCTIONS = ("sin", "cos", "tan", "log", "ln")
_POWERS = re.compile(r"\^(-?\w+|\([^()]*\))")


def looks_like_math(label: str) -> bool:
    """True when the label carries math notation, not prose.

    Prose stays plain text: setting a sentence in math mode makes every space
    and letter italic and unreadable.
    """
    return _MATH_HINT.search(label) is not None


def latex_expression(expr: str) -> str:
    """A Python expression as LaTeX: ``1 + x + x**2/2`` -> ``1 + x + x^{2}/2``.

    Storyboards carry expressions the way Python writes them, and a text widget
    prints them as source code -- the exponent stays a literal ``**2``. Any
    place that shows an equation (a graph's title, its legend) uses this, so
    the math reads like math instead of like a line of Python.
    """
    text = " ".join(expr.split()).replace("**", "^")
    text = _POWERS.sub(lambda m: "^{" + m.group(1).strip("()") + "}", text)
    text = re.sub(r"\bexp\(([^()]*)\)", lambda m: "e^{" + m.group(1) + "}", text)
    for name in _FUNCTIONS:
        text = re.sub(
            rf"\b{name}\(([^()]*)\)",
            lambda m, name=name: "\\" + name + "(" + m.group(1) + ")",
            text,
        )
    text = re.sub(r"\bsqrt\(([^()]*)\)", lambda m: "\\sqrt{" + m.group(1) + "}", text)
    return re.sub(r"\s*\*\s*", r" \\cdot ", text)


def split_terms(latex: str) -> list[str]:
    """The top-level ``+`` terms of a LaTeX sum, so a long one can be shortened."""
    return [part for part in re.split(r"\s\+\s", latex) if part.strip()]


def fit(
    mobject: Any,
    max_width: float | None = None,
    max_height: float | None = None,
    scale_up: bool = True,
) -> Any:
    """Scale a mobject to fit inside the frame with margins.

    First scales down if the mobject exceeds the frame bounds, then optionally
    scales up proportionally to fill the available space. Content never
    overflows the frame because the up-scale is limited by whichever dimension
    is more constraining.

    Set ``scale_up=False`` to only shrink content that is too large, leaving
    smaller content at its natural size. This is useful for text/math content
    that should keep comfortable side margins rather than expanding to fill
    the frame.
    """
    from manim import config
    max_width = max_width or config.frame_width - 1.0
    max_height = max_height or config.frame_height - 2.4  # bottom band reserved for caption
    if mobject.width > max_width:
        mobject.scale_to_fit_width(max_width)
    if mobject.height > max_height:
        mobject.scale_to_fit_height(max_height)
    # Scale up proportionally to fill the frame when content is smaller than
    # the bounds. Limited by min(scale_w, scale_h) so content never overflows.
    if scale_up:
        scale_w = max_width / mobject.width if mobject.width > 0 else 1.0
        scale_h = max_height / mobject.height if mobject.height > 0 else 1.0
        scale = min(scale_w, scale_h)
        if scale > 1.0:
            mobject.scale(scale)
    return mobject


class Clock:
    """Tracks time spent so a beat takes exactly its declared duration.

    The video is written in whole frames: Manim rounds every animation up to
    the next frame, so a run time that is not a whole number of frames makes
    the video longer than the beat declared. A beat with many small
    animations accumulates that rounding -- the recursion tree had 29 of them
    and its video was 0.6s longer than its 5.2s beat. A component that
    budgets in frames (``frames()`` / ``seconds()``) cannot drift.
    """

    def __init__(self, scene: Any, total: float, fps: float | None = None) -> None:
        # --narrate: the scene sets ``narration_hold`` when narration outlasts the beat. Adding it
        # to the budget holds the content *before* the closing fade-out, not a blank frame after it.
        hold = getattr(scene, "narration_hold", 0.0)
        self.scene, self.total, self.used = scene, total + (hold if isinstance(hold, (int, float)) else 0.0), 0.0
        self.fps = float(fps) if fps else frame_rate()

    def frames(self, seconds: float) -> int:
        """How many whole video frames `seconds` is worth."""
        return max(0, int(round(seconds * self.fps)))

    def seconds(self, frames: int) -> float:
        """`frames` whole video frames, in seconds."""
        return frames / self.fps

    def whole(self, seconds: float) -> float:
        """`seconds`, rounded to the nearest whole video frame."""
        return self.seconds(self.frames(seconds))

    def play(self, *animations: Any, run_time: float) -> None:
        self.scene.play(*animations, run_time=run_time)
        self.used += run_time

    def wait(self, seconds: float) -> None:
        if seconds > 1e-6:
            self.scene.wait(seconds)
            self.used += seconds

    def finish(self, fade_out: float = FADE_OUT) -> None:
        """Hold until the budget minus the fade, then fade everything out."""
        from manim import FadeOut
        if self.used + fade_out > self.total + 0.05:
            warn(self.scene, f"timing: a beat ran {self.used + fade_out - self.total:.1f}s longer than its declared "
                             f"{self.total:.1f}s; captions may drift")
        self.wait(max(0.0, self.total - fade_out - self.used))
        if self.scene.mobjects:
            self.play(*[FadeOut(m) for m in self.scene.mobjects], run_time=fade_out)
        else:
            self.wait(fade_out)
        self.wait(max(0.0, self.total - self.used))


#: Fraction of each frame edge that frame-lint keeps free of content.
SAFE_AREA_MARGIN = 0.05

#: Buffer between the frame's bottom edge and the caption's bottom edge.
#: Must exceed ``SAFE_AREA_MARGIN`` so the caption's descenders stay out of
#: the safe-area band; 0.055 is the smallest value that clears it.
CAPTION_BOTTOM_BUFF = 0.055

#: Gap kept between the caption's top and the bottom of the content above it.
CAPTION_CONTENT_GAP = 0.25

#: Leading between two caption lines, in frame units. The caption is one Text
#: per line, so the lines are placed on their own baselines: the leading is
#: an absolute distance in the frame, not a fraction of the font size, so it
#: stays the same when a caption is scaled down to fit the width.
CAPTION_LINE_LEADING = 0.85


def _text_baseline(text: Any) -> float:
    """The y a one-line Text rests on: its baseline.

    Most letters stand on the baseline; the few that hang below it (g, j, p,
    q, y) do not. The bottom that most of the glyphs share is therefore the
    baseline, and it is what the caption's lines are lined up on.
    """
    bottoms = [float(g.get_bottom()[1]) for g in text.submobjects]
    if not bottoms:
        return float(text.get_bottom()[1])
    best, count = bottoms[0], 0
    for candidate in bottoms:
        hits = sum(1 for b in bottoms if abs(b - candidate) <= 0.02)
        if hits > count:
            best, count = candidate, hits
    return best


def make_caption(text: str, colors: ThemeColors) -> Any:
    """Burned-in caption pinned to the bottom edge, sized for actual frame dimensions.

    Uses ``config.frame_width`` / ``config.frame_height`` (set by ``manim render
    -r ...``) so caption font and wrap width adapt to portrait (9:16) and
    landscape frames. For a 5.6x10.0 frame the font scales up ~1.8x and the
    wrap width scales down to ~28 chars so the caption stays readable and
    within the safe area.

    The caption is only scaled *down* when it would overflow the frame with
    horizontal margins; short captions are never enlarged to fill the frame,
    which previously made tiny captions unreadably large and edge-to-edge.

    It is pinned clear of the ``SAFE_AREA_MARGIN`` band: a caption closer to
    the edge puts its descenders inside that band, and frame-lint then warns
    about every single frame of the video.

    **One Text per line, deliberately** (issue #31). A single Text holding
    several lines is drawn *twice* by Manim as soon as it is as wide as the
    frame: the first line comes back as a ghost a few pixels off, over the
    caption itself, and the text is unreadable. The mobject is not
    duplicated -- it holds one set of glyphs -- but the render is, so the
    caption is built as one Text per line and the lines are put together
    here. Word-by-word pieces are still not the answer: they lose the shared
    baseline and the word gaps, and the rendered caption read "termbrings"
    and "legendis". Typesetting math inside a caption needs one block per
    line, driven by a measured baseline, and that is its own card.
    """
    from manim import DOWN, RIGHT, UP, Text, VGroup, config

    frame_width = config.frame_width
    frame_height = config.frame_height

    # Baseline: landscape (12.4 x 5.6). Scale font with frame height.
    font_size = 28 * (frame_height / 5.6)
    # Cap at 40 so very tall frames don't produce unreadably large text.
    font_size = min(font_size, 40)
    # Wrap width scales with frame width, but never below 20 chars so very
    # narrow frames still produce readable (if narrow) captions.
    wrap_width = max(20, int(62 * (frame_width / 12.4)))

    lines = wrap(text, wrap_width).split("\n")
    pieces = [Text(line, font_size=font_size, color=colors.muted) for line in lines]

    # Only scale down if the caption is too wide for the frame with margins.
    # Never scale up: short captions stay at their natural readable size.
    # 5% horizontal margin on each side keeps captions from touching the edge.
    # The lines are scaled before they are put together, so the leading
    # between them is the same in frame units however much the text shrinks.
    max_caption_width = frame_width * 0.9
    natural_width = max((piece.width for piece in pieces), default=0.0)
    if natural_width > max_caption_width:
        for piece in pieces:
            piece.scale(max_caption_width / natural_width)

    # Put the lines on their own baselines: the same distance between the
    # baselines whatever the lines contain, so the caption reads as one
    # block of text.
    if len(pieces) > 1:
        baselines = [_text_baseline(piece) for piece in pieces]
        for i, (piece, base) in enumerate(zip(pieces, baselines)):
            piece.shift(UP * (baselines[0] - CAPTION_LINE_LEADING * i - base))
        left = min(piece.get_left()[0] for piece in pieces)
        for piece in pieces:
            piece.shift(RIGHT * (left - piece.get_left()[0]))

    cap = VGroup(*pieces)
    # The caption is centred in the frame, as it was when it was one Text.
    cap.shift(RIGHT * -cap.get_center()[0])
    cap.to_edge(DOWN, buff=frame_height * CAPTION_BOTTOM_BUFF)
    return cap


def caption_band_top(caption: Any = None) -> float:
    """Y coordinate above which content must stay to leave room for the caption.

    The caption's height depends on how its text wraps, so the band cannot be
    a constant: a one-line caption leaves more room than a two-line one.
    Layout code uses this to decide how much vertical space it may use.

    Pass the real caption mobject (the scene builds one per beat and keeps it
    on ``scene.caption_mobject``) to get its exact top. With no caption on
    screen there is nothing to collide with, but content must still stay out
    of the safe-area band, so the band is the frame's bottom edge plus the
    safe-area margin and a small gap.
    """
    from manim import config

    if caption is not None:
        return caption.get_top()[1] + CAPTION_CONTENT_GAP
    return (
        -config.frame_height / 2
        + SAFE_AREA_MARGIN * config.frame_height
        + CAPTION_CONTENT_GAP
    )


def fit_in_room(scene: Any, mobject: Any, scale_up: bool = True) -> Any:
    """Fit a mobject into the room the caption leaves, and centre it there.

    The room runs from the top safe margin down to the real caption's band
    (``caption_band_top``), and across the side safe margins. A two-line caption
    is taller than a one-line one, so the room is measured from the caption the
    scene actually holds, never assumed. Use this instead of ``fit`` for the
    final layout of a component, which centres in the whole frame and so runs
    into a tall caption.
    """
    from manim import config

    top = config.frame_height * (0.5 - SAFE_AREA_MARGIN) - 0.3
    band = caption_band_top(getattr(scene, "caption_mobject", None))
    width = config.frame_width * (1 - 2 * SAFE_AREA_MARGIN) - 0.3
    fit(mobject, max_width=width, max_height=top - band, scale_up=scale_up)
    mobject.move_to([0.0, (top + band) / 2, 0.0])
    return mobject


def caption_strip_fraction(caption: Any = None, frame_height: float = 8.0) -> float:
    """The fraction of the frame height the burned-in caption covers.

    Derived from the caption band instead of guessed: the caption is pinned
    CAPTION_BOTTOM_BUFF above the bottom edge and the band says where the
    content has to stop, so everything between the bottom edge and the
    caption's top is caption rather than content. How tall that is depends
    on how the caption's text wraps -- a three-line caption needs a bigger
    strip than a one-line one -- which is why it cannot be a constant.

    Without a caption there is nothing to leave out: the strip is zero.
    """
    if caption is None:
        return 0.0
    caption_top = caption_band_top(caption) - CAPTION_CONTENT_GAP
    frame_bottom = -frame_height / 2
    # The strip is measured from the bottom edge, because that is how the
    # lint leaves it out: the caption is pinned above the bottom edge, so the
    # strip covers the caption and the empty space under it.
    return max(0.0, (caption_top - frame_bottom) / frame_height)


def clear_stage(scene: Any) -> None:
    """Remove everything except the burned-in caption."""
    keep = getattr(scene, "caption_mobject", None)
    for m in list(scene.mobjects):
        if m is not keep:
            scene.remove(m)


def text_card(scene: Any, text: str, colors: ThemeColors, total: float) -> None:
    """Fallback card used when a component fails: shows plain text for `total` seconds."""
    from manim import FadeIn, Text
    clear_stage(scene)
    t = fit(Text(wrap(text, 40), font_size=MIN_FONT_SIZE + 8, color=colors.text))
    clock = Clock(scene, total)
    clock.play(FadeIn(t), run_time=min(0.6, total / 3))
    clock.finish()


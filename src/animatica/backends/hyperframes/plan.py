"""Renderer-neutral layout and timing plan for the HyperFrames backend.

The plan is the seam between the (validated, model-authored) storyboard and the
(trusted, hand-written) HTML template.  It answers, in tested Python:

* when does each beat start and end (seconds on a single composition timeline);
* where does every line of text sit (absolute pixels on a 1280x720 stage);
* when does that line appear (seconds after its beat starts).

The template may only draw what is in the plan.  It must not compute geometry
or timing itself -- that is what produced the "outline 80 px off the array" and
"hard-coded act boundaries" defects in the two hand-authored pilots.

This module is pure Python: no Node, no browser, no Manim, no ffmpeg.  It is
therefore fully unit-testable, which is the point.

Text measurement is a *deterministic estimate*, not real font metrics: average
glyph width is ``CHAR_W`` times the font size, wide (CJK) characters count as
two.  The estimate is deliberately conservative, and a real browser check
(``npx hyperframes check``) is still the final word on overflow.
"""
from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from animatica.components._latex import latex_to_plain
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.storyboard.models import Storyboard

# ---------------------------------------------------------------------------
# Stage constants (pixels, top-left origin; matches the 1280x720 composition)
# ---------------------------------------------------------------------------

STAGE_W = 1280
STAGE_H = 720
MARGIN = 80

BODY_TOP = MARGIN
BODY_BOTTOM = STAGE_H - MARGIN  # 640
CAPTION_H = 56
CAPTION_GAP = 28
CAPTION_TOP = BODY_BOTTOM - CAPTION_H  # 584
BODY_BOTTOM_WITH_CAPTION = CAPTION_TOP - CAPTION_GAP  # 556
SAFE_RIGHT = STAGE_W - MARGIN  # 1200
BODY_W = SAFE_RIGHT - MARGIN  # 1120

CHAR_W = 0.54  # average glyph width as a fraction of font size
LINE_H = 1.32  # line height as a multiple of font size

TITLE_SIZE = 64
SUBTITLE_SIZE = 26
EQUATION_SIZE = 44
STEP_SIZE = 30
CAPTION_SIZE = 22

STEP_NUMBER_W = 56
STEP_GAP = 18

#: Components this backend can lay out. Everything else is rejected *before*
#: rendering, with an actionable message, so a model never gets a half video.
SUPPORTED_COMPONENTS = frozenset({"title_card", "equation", "steps_list"})


class PlanError(ValueError):
    """A storyboard cannot be planned by this backend."""


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def within(self, area: "Rect", tol: float = 0.5) -> bool:
        return (
            self.x >= area.x - tol
            and self.y >= area.y - tol
            and self.right <= area.right + tol
            and self.bottom <= area.bottom + tol
        )

    def overlaps(self, other: "Rect", pad: float = 0.0) -> bool:
        return not (
            self.right + pad <= other.x
            or other.right + pad <= self.x
            or self.bottom + pad <= other.y
            or other.bottom + pad <= self.y
        )


SAFE_AREA = Rect(MARGIN, BODY_TOP, BODY_W, BODY_BOTTOM - BODY_TOP)
CAPTION_AREA = Rect(MARGIN, CAPTION_TOP, BODY_W, CAPTION_H)


def _units(text: str) -> float:
    """Text width in glyph units: wide/full-width characters count double."""
    return sum(
        2.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 1.0 for ch in text
    )


def text_width(text: str, size: int) -> float:
    return round(_units(text) * size * CHAR_W, 2)


def line_height(size: int) -> float:
    return round(size * LINE_H, 2)


def wrap(text: str, size: int, max_w: float) -> list[str]:
    """Greedy word wrap using estimated widths. Never returns an empty list."""
    text = " ".join(text.split())
    if not text:
        return [""]
    limit = max(1.0, max_w / (size * CHAR_W))
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = word if not current else current + " " + word
        if _units(candidate) <= limit:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # A single word wider than the line: hard-split on character units.
        while _units(word) > limit:
            cut = 0
            acc = 0.0
            for ch in word:
                step = 2.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 1.0
                if acc + step > limit:
                    break
                acc += step
                cut += 1
            cut = max(1, cut)
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Plan data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """One rendered line of text, positioned in stage pixels."""

    text: str
    x: float
    y: float
    w: float
    h: float
    size: int
    color: str = "text"  # semantic token, resolved by the theme in the template
    weight: int = 700
    align: str = "left"  # "left" | "center"
    reveal: float = 0.0  # seconds after the beat starts
    role: str = "body"  # body | number | caption

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)


@dataclass(frozen=True)
class BeatPlan:
    scene: int  # 1-based scene index
    index: int  # 1-based beat index within its scene
    component: str
    start: float  # seconds, absolute on the composition timeline
    duration: float
    lines: tuple[Line, ...] = ()
    caption: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def end(self) -> float:
        return round(self.start + self.duration, 3)

    @property
    def body_lines(self) -> tuple[Line, ...]:
        return tuple(line for line in self.lines if line.role != "caption")

    @property
    def caption_line(self) -> Line | None:
        return next((line for line in self.lines if line.role == "caption"), None)


@dataclass(frozen=True)
class Plan:
    title: str
    beats: tuple[BeatPlan, ...]
    width: int = STAGE_W
    height: int = STAGE_H

    @property
    def duration(self) -> float:
        return round(max((beat.end for beat in self.beats), default=0.0), 3)

    @property
    def scene_count(self) -> int:
        return len({beat.scene for beat in self.beats})

    def line_count(self) -> int:
        return sum(len(beat.lines) for beat in self.beats)

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready payload for the template. The template draws this, nothing else."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Beat builders
# ---------------------------------------------------------------------------


def _centered(text: str, size: int, y: float, **kw: Any) -> Line:
    w = text_width(text, size)
    return Line(
        text=text,
        x=round((STAGE_W - w) / 2, 2),
        y=round(y, 2),
        w=w,
        h=line_height(size),
        size=size,
        align="center",
        **kw,
    )


def _body_bottom(has_caption: bool) -> float:
    return BODY_BOTTOM_WITH_CAPTION if has_caption else BODY_BOTTOM


def _plan_title_card(params: Any, has_caption: bool) -> tuple[list[Line], dict[str, Any]]:
    title_lines = wrap(params.title, TITLE_SIZE, BODY_W)
    subtitle_lines = wrap(params.subtitle, SUBTITLE_SIZE, BODY_W) if params.subtitle.strip() else []

    title_h = line_height(TITLE_SIZE) * len(title_lines)
    sub_h = line_height(SUBTITLE_SIZE) * len(subtitle_lines)
    gap = 24.0
    total = title_h + (gap + sub_h if subtitle_lines else 0.0)

    bottom = _body_bottom(has_caption)
    y = BODY_TOP + max(0.0, ((bottom - BODY_TOP) - total) / 2)

    lines: list[Line] = []
    for i, text in enumerate(title_lines):
        lines.append(_centered(text, TITLE_SIZE, y + i * line_height(TITLE_SIZE), reveal=round(0.15 + 0.06 * i, 2)))
    y += title_h + (gap if subtitle_lines else 0.0)
    for i, text in enumerate(subtitle_lines):
        lines.append(
            _centered(
                text,
                SUBTITLE_SIZE,
                y + i * line_height(SUBTITLE_SIZE),
                reveal=round(0.55 + 0.06 * i, 2),
                color="muted",
                weight=500,
            )
        )
    return lines, {"title_lines": len(title_lines), "subtitle_lines": len(subtitle_lines)}


def _plan_equation(params: Any, duration: float, has_caption: bool) -> tuple[list[Line], dict[str, Any]]:
    entries: list[tuple[str, str]] = [(src, latex_to_plain(src)) for src in params.latex]

    wrapped: list[str] = []
    for _src, plain in entries:
        wrapped.extend(wrap(plain, EQUATION_SIZE, BODY_W))

    total = line_height(EQUATION_SIZE) * len(wrapped) + 28.0 * max(0, len(wrapped) - 1)
    bottom = _body_bottom(has_caption)
    y = BODY_TOP + max(0.0, ((bottom - BODY_TOP) - total) / 2)

    step = max(0.5, (duration - 0.75) / max(1, len(wrapped)))
    lines: list[Line] = []
    for i, text in enumerate(wrapped):
        lines.append(
            _centered(
                text,
                EQUATION_SIZE,
                y + i * (line_height(EQUATION_SIZE) + 28.0),
                reveal=round(0.25 + i * step, 2),
                weight=500,
            )
        )
    return lines, {"equations": len(entries), "plain_text": [plain for _src, plain in entries]}


def _plan_steps(params: Any, duration: float, has_caption: bool) -> tuple[list[Line], dict[str, Any]]:
    items: list[str] = list(params.items)
    bottom = _body_bottom(has_caption)
    top = float(BODY_TOP)

    chosen: tuple[int, float, list[list[str]]] | None = None
    for size, gap in ((STEP_SIZE, STEP_GAP), (27, 12), (24, 8)):
        rows = [wrap(item, size, BODY_W - STEP_NUMBER_W) for item in items]
        height = sum(len(r) for r in rows) * line_height(size) + gap * max(0, len(rows) - 1)
        if height <= bottom - top:
            chosen = (size, gap, rows)
            break
    if chosen is None:
        raise PlanError(
            f"steps_list: {len(items)} items of text do not fit on one 1280x720 slide even at "
            f"{24}px. Split the list across two beats, or shorten the items."
        )

    size, gap, rows = chosen
    height = sum(len(r) for r in rows) * line_height(size) + gap * max(0, len(rows) - 1)
    # Centre the block vertically, like the Manim component does; falls back to
    # the top of the body area when the rows are too tall to centre.
    y = top + max(0.0, (bottom - top - height) / 2)
    lines: list[Line] = []
    line_h = line_height(size)
    for i, row in enumerate(rows, 1):
        reveal = round(0.4 + (i - 1) * 1.5, 2)
        number = f"{i}."
        lines.append(
            Line(
                text=number,
                x=float(MARGIN),
                y=round(y, 2),
                w=text_width(number, size),
                h=line_h,
                size=size,
                color="accent",
                role="number",
                reveal=reveal,
            )
        )
        for j, text in enumerate(row):
            lines.append(
                Line(
                    text=text,
                    x=float(MARGIN + STEP_NUMBER_W),
                    y=round(y + j * line_h, 2),
                    w=text_width(text, size),
                    h=line_h,
                    size=size,
                    reveal=reveal,
                    weight=500,
                )
            )
        y += len(row) * line_h + gap
    return lines, {"items": len(items), "size": size, "gap": gap}


def _caption_line(text: str) -> Line:
    w = min(text_width(text, CAPTION_SIZE), BODY_W)
    return Line(
        text=text,
        x=round((STAGE_W - w) / 2, 2),
        y=float(CAPTION_TOP + 8),
        w=w,
        h=line_height(CAPTION_SIZE),
        size=CAPTION_SIZE,
        color="muted",
        weight=500,
        align="center",
        role="caption",
    )


_BUILDERS = {
    "title_card": lambda params, duration, has_caption: _plan_title_card(params, has_caption),
    "equation": _plan_equation,
    "steps_list": _plan_steps,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def plan_storyboard(
    sb: Storyboard,
    registry: ComponentRegistry | None = None,
    captions: bool = True,
) -> Plan:
    """Plan every beat of ``sb`` onto one absolute timeline, in stage pixels.

    ``captions=False`` drops the burned-in caption band *and* gives the body the
    full stage height, so ``--no-captions`` never leaves an unexplained gap.

    Raises :class:`PlanError` when a component is not supported by this backend
    or its params cannot be laid out.  Layout *quality* problems (overflow,
    overlap) are reported separately by :func:`problems` so that a caller can
    render a diagnosis instead of failing silently.
    """
    reg = registry or default_registry()
    beats: list[BeatPlan] = []
    clock = 0.0

    for si, scene in enumerate(sb.scenes, 1):
        for bi, beat in enumerate(scene.beats, 1):
            where = f"scene {si}, beat {bi} ({beat.component})"
            if beat.component not in SUPPORTED_COMPONENTS:
                supported = ", ".join(sorted(SUPPORTED_COMPONENTS))
                raise PlanError(
                    f"{where}: the HyperFrames backend cannot draw this component yet. "
                    f"Supported here: {supported}. Keep other components on the manim backend."
                )
            if beat.component not in reg.names():
                raise PlanError(f"{where}: component {beat.component!r} is not registered.")
            component = reg.get(beat.component)
            try:
                params = component.Params.model_validate(beat.params)
            except Exception as exc:  # pydantic message already names the field
                raise PlanError(f"{where}: invalid params: {exc}") from exc

            duration = float(component.duration(params))
            caption = beat.caption.strip() if captions else ""
            build = _BUILDERS[beat.component]
            lines, meta = build(params, duration, bool(caption))
            if caption:
                lines.append(_caption_line(caption))
            beats.append(
                BeatPlan(
                    scene=si,
                    index=bi,
                    component=beat.component,
                    start=round(clock, 3),
                    duration=round(duration, 3),
                    lines=tuple(lines),
                    caption=caption,
                    meta=meta,
                )
            )
            clock += duration

    return Plan(title=sb.title, beats=tuple(beats))


# ---------------------------------------------------------------------------
# Layout diagnostics (the checks the pilots never had)
# ---------------------------------------------------------------------------


def problems(plan: Plan) -> list[str]:
    """Return human-readable layout defects, one per problem. Empty means clean.

    Messages name the beat, the line and the offending numbers, so an agent can
    fix the storyboard without re-rendering a video to find out what is wrong.
    """
    out: list[str] = []

    for beat in plan.beats:
        where = f"scene {beat.scene}, beat {beat.index} ({beat.component})"
        if beat.duration <= 0:
            out.append(f"{where}: duration must be positive, got {beat.duration}")
        if not beat.body_lines:
            out.append(f"{where}: nothing to draw (no text lines)")

        body = beat.body_lines
        for line in body:
            if not line.text.strip():
                out.append(f"{where}: an empty text line would be drawn at y={line.y}")
                continue
            if not line.rect.within(SAFE_AREA):
                out.append(
                    f"{where}: {line.text!r} at ({line.x}, {line.y}) {line.w}x{line.h} "
                    f"leaves the safe area {SAFE_AREA.x}..{SAFE_AREA.right} x "
                    f"{SAFE_AREA.y}..{SAFE_AREA.bottom}"
                )
            if not (0.0 <= line.reveal <= beat.duration):
                out.append(
                    f"{where}: {line.text!r} is revealed at {line.reveal}s, "
                    f"outside the beat's 0..{beat.duration}s"
                )

        for i, a in enumerate(body):
            for b in body[i + 1:]:
                if a.rect.overlaps(b.rect):
                    out.append(
                        f"{where}: {a.text!r} and {b.text!r} overlap "
                        f"({a.rect.x},{a.rect.y},{a.rect.w},{a.rect.h} vs "
                        f"{b.rect.x},{b.rect.y},{b.rect.w},{b.rect.h})"
                    )

        caption = beat.caption_line
        if caption is not None:
            if not caption.rect.within(CAPTION_AREA):
                out.append(
                    f"{where}: caption {caption.text!r} does not sit in the caption band "
                    f"{CAPTION_AREA.x}..{CAPTION_AREA.right} x {CAPTION_AREA.y}..{CAPTION_AREA.bottom}"
                )
            for line in body:
                if line.rect.bottom > BODY_BOTTOM_WITH_CAPTION + 0.5:
                    out.append(
                        f"{where}: {line.text!r} reaches y={line.rect.bottom}, "
                        f"into the caption band (body must end by {BODY_BOTTOM_WITH_CAPTION})"
                    )

    return out


def overlapping_pairs(plan: Plan) -> Iterable[tuple[Line, Line]]:  # pragma: no cover - debug helper
    """Yield body line pairs that overlap in the same beat (for ad-hoc debugging)."""
    for beat in plan.beats:
        body = beat.body_lines
        for i, a in enumerate(body):
            for b in body[i + 1:]:
                if a.rect.overlaps(b.rect):
                    yield a, b

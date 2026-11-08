"""Compose a :class:`~animatica.backends.hyperframes.plan.Plan` into one HTML file.

The composition is the *trusted* half of the seam:

* the template is tracked source (``template.html`` next to this module);
* geometry, timing and colour tokens are written into ``data-*`` attributes and
  an inline ``style`` built only from numbers and whitelisted tokens;
* storyboard text is written as escaped text nodes and never enters a script,
  an attribute, a CSS value or a URL;
* the file is a pure function of the plan -- no timestamps, no randomness, no
  network references -- so the same storyboard always produces byte-identical
  HTML (see ``content_hash``).

No browser is needed to build or test a composition. A browser is only needed
to *look* at one.
"""
from __future__ import annotations

import hashlib
from html import escape
from importlib import resources
from pathlib import Path

from animatica.backends.hyperframes.plan import BeatPlan, Line, Plan

COMPOSITION_ID = "animatica-plan"
FPS = 24

STAGE_MARKER = "__ANIMATICA_STAGE_ATTRS__"
TITLE_MARKER = "__ANIMATICA_TITLE__"
BEATS_MARKER = "__ANIMATICA_BEATS__"

#: Semantic colour tokens the plan may use. The template defines each one; an
#: unknown token is a programming error, not something to guess at.
COLOR_CLASSES = {
    "text": "c-text",
    "muted": "c-muted",
    "accent": "c-accent",
}

_ROLE_CLASSES = {
    "body": "",
    "number": "role-number",
    "caption": "l-caption",
}


def _num(value: float | int) -> str:
    """Format a plan number for CSS/attributes without exponent or trailing zeros."""
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _esc(text: str) -> str:
    return escape(text, quote=True)


def _load_template() -> str:
    return resources.files(__package__).joinpath("template.html").read_text(encoding="utf-8")


def _line_html(line: Line) -> str:
    color = COLOR_CLASSES.get(line.color)
    if color is None:
        raise ValueError(
            f"unknown colour token {line.color!r}; valid tokens: {', '.join(sorted(COLOR_CLASSES))}"
        )
    role = _ROLE_CLASSES.get(line.role)
    if role is None:
        raise ValueError(f"unknown line role {line.role!r}")
    classes = " ".join(part for part in ("line", color, role) if part)
    style = (
        f"left:{_num(line.x)}px;"
        f"top:{_num(line.y)}px;"
        f"width:{_num(line.w)}px;"
        f"font-size:{_num(line.size)}px;"
        f"font-weight:{_num(line.weight)};"
        f"text-align:{line.align};"
    )
    return (
        f'<div class="{classes}" data-reveal="{_num(line.reveal)}" style="{style}">'
        f"{_esc(line.text)}</div>"
    )


def _beat_html(beat: BeatPlan) -> str:
    label = f"scene {beat.scene} beat {beat.index}: {beat.component}"
    lines = "\n".join("    " + _line_html(line) for line in beat.lines)
    return (
        f'<section id="scene-{beat.scene}-beat-{beat.index}" class="beat clip" '
        f'data-start="{_num(beat.start)}" data-duration="{_num(beat.duration)}" '
        f'data-scene="{beat.scene}" data-beat="{beat.index}" '
        f'data-component="{_esc(beat.component)}" aria-label="{_esc(label)}">\n'
        f"{lines}\n</section>"
    )


def render_html(plan: Plan) -> str:
    """Return the complete, deterministic HTML composition for ``plan``.

    Call :func:`animatica.backends.hyperframes.plan.problems` first if you want
    to reject a bad layout; this function renders whatever it is given.
    """
    if not plan.beats:
        raise ValueError("cannot compose a plan with no beats")

    stage_attrs = (
        f'data-composition-id="{COMPOSITION_ID}" data-start="0" '
        f'data-duration="{_num(plan.duration)}" data-width="{plan.width}" '
        f'data-height="{plan.height}" data-fps="{FPS}"'
    )
    html = _load_template()
    html = html.replace(STAGE_MARKER, stage_attrs)
    html = html.replace(TITLE_MARKER, _esc(plan.title))
    html = html.replace(BEATS_MARKER, "\n  ".join(_beat_html(beat) for beat in plan.beats))

    for marker in (STAGE_MARKER, TITLE_MARKER, BEATS_MARKER):
        if marker in html:  # pragma: no cover - guards template/composer drift
            raise RuntimeError(f"template marker {marker} was not substituted")
    return html


def content_hash(html: str) -> str:
    """sha256 of the composition, for determinism checks and cache keys."""
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def write_composition(plan: Plan, out_dir: Path) -> Path:
    """Write ``index.html`` (HyperFrames' composition entry point) into ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(render_html(plan), encoding="utf-8", newline="\n")
    return path

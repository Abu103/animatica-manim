"""Code diff: the lines that change between two versions of a snippet, red for removed and green for added.

Made for prompts like "show the diff when replacing 3.14 with math.pi" or "before and after of this refactor".
Give the full `before` and `after` text; the diff is computed, so it is always correct. Unchanged lines show
dimmed for context. At most 12 diff lines, 48 characters each. Not syntax-highlighted: colour means
added/removed here. Duration: 2.5 s + 0.5 s per changed line.
"""
from __future__ import annotations

import difflib
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from animatica.components._draw import Clock, fit_in_room, prepare, unescape_code
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_ROWS = 12
MAX_CHARS = 48


def _lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").rstrip("\n")
    return text.split("\n") if text else []


class CodeDiff(Component):
    name: ClassVar[str] = "code_diff"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        before: str = Field(max_length=800)
        after: str = Field(max_length=800)

        _unescape = field_validator("before", "after", mode="before")(unescape_code)

        @model_validator(mode="after")
        def _check(self):
            rows = CodeDiff.diff_rows(self.before, self.after)
            if not any(op != "keep" for op, _ in rows):
                raise ValueError("before and after have no difference")
            if len(rows) > MAX_ROWS:
                raise ValueError(f"the diff is {len(rows)} lines, more than {MAX_ROWS}: show a smaller piece of the code")
            for _, text in rows:
                if len(text) > MAX_CHARS:
                    raise ValueError(f"a line is longer than {MAX_CHARS} characters: {text[:30]!r}...")
            return self

    @staticmethod
    def diff_rows(before: str, after: str) -> list[tuple[str, str]]:
        """The diff as (op, text) rows, op one of keep/remove/add; removals come before additions."""
        a, b = _lines(before), _lines(after)
        rows: list[tuple[str, str]] = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                rows += [("keep", t) for t in a[i1:i2]]
            else:
                rows += [("remove", t) for t in a[i1:i2]]
                rows += [("add", t) for t in b[j1:j2]]
        return rows

    @staticmethod
    def indent(text: str, tab: int = 4) -> tuple[int, str]:
        """(leading columns, the rest). Manim drops leading spaces when it places text, so the
        indentation is measured here and put back as an offset: in Python it is part of the meaning."""
        col = 0
        for i, ch in enumerate(text):
            if ch == " ":
                col += 1
            elif ch == "\t":
                col += tab - col % tab
            else:
                return col, text[i:]
        return 0, ""

    @staticmethod
    def _changed(p: BaseModel) -> int:
        return sum(op != "keep" for op, _ in CodeDiff.diff_rows(p.before, p.after))  # type: ignore[attr-defined]

    def duration(self, p: BaseModel) -> float:
        return 2.5 + 0.5 * self._changed(p)

    def fallback_text(self, p: BaseModel) -> str:
        mark = {"keep": " ", "remove": "-", "add": "+"}
        rows = self.diff_rows(p.before, p.after)  # type: ignore[attr-defined]
        return "\n".join([p.title] + [f"{mark[op]}{text}" for op, text in rows])  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, LEFT, FadeIn, ManimColor, Rectangle, Text, VGroup

        prepare(scene, colors)
        green, red = "#3fb950", "#f85149"
        rows = self.diff_rows(p.before, p.after)

        char_w = Text("0" * 20, font="Monospace", font_size=32).width / 20  # one monospace column

        def row(op: str, text: str):
            cols, text = self.indent(text)
            glyph = {"keep": "", "remove": "-", "add": "+"}[op]
            glyph_color = {"keep": colors.muted, "remove": red, "add": green}[op]
            code = None
            if text:  # a blank line has nothing to draw: an empty Text has no geometry to place
                code = Text(text, font="Monospace", font_size=32, color=colors.muted if op == "keep" else colors.text)
            # the tint hugs the text: a wide dim band would drag the frame's average contrast down
            band_w = (code.width if code is not None else 0.0) + cols * char_w + 1.0
            tint = {"keep": colors.background, "remove": red, "add": green}[op]
            band = Rectangle(width=band_w, height=0.5, fill_color=ManimColor(tint),
                             fill_opacity=0.0 if op == "keep" else 0.28, stroke_width=0)
            parts = [band]
            if glyph:
                parts.append(Text(glyph, font="Monospace", font_size=32, color=glyph_color).align_to(band, LEFT).shift([0.15, 0, 0]))
            if code is not None:
                parts.append(code.align_to(band, LEFT).shift([0.55 + cols * char_w, 0, 0]))
            return VGroup(*parts)

        built = [row(op, text) for op, text in rows]
        stack = VGroup(*built).arrange(DOWN, buff=0.04, aligned_edge=LEFT)
        body = VGroup(Text(p.title, font_size=40, color=colors.text), stack).arrange(DOWN, buff=0.45)
        fit_in_room(scene, body)

        clock = Clock(scene, self.duration(p))
        context = [g for g, (op, _) in zip(built, rows) if op == "keep"]
        clock.play(FadeIn(body[0]), *[FadeIn(g) for g in context], run_time=clock.whole(0.6))
        for g, (op, _) in zip(built, rows):
            if op != "keep":
                clock.play(FadeIn(g), run_time=clock.whole(0.5))
        clock.finish()

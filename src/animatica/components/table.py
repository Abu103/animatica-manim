"""Table: a small grid whose rows fade in one by one. Max 6 columns x 6 rows.

Duration: 2.0 s + 0.5 s per row.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_COLS = 6
MAX_ROWS = 6


class Table(Component):
    name: ClassVar[str] = "table"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        columns: list[str] = Field(min_length=1, max_length=MAX_COLS)
        rows: list[list[str]] = Field(min_length=1, max_length=MAX_ROWS)

        @model_validator(mode="after")
        def _check(self):
            n = len(self.columns)
            for i, row in enumerate(self.rows, 1):
                if len(row) != n:
                    raise ValueError(f"row {i} has {len(row)} cells, expected {n} (one per column)")
                if any(len(c) > MAX_TEXT for c in row):
                    raise ValueError("cell text too long")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.5 * len(p.rows)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [" | ".join(p.columns)]  # type: ignore[attr-defined]
        lines += [" | ".join(r) for r in p.rows]  # type: ignore[attr-defined]
        return p.title + ":\n" + "\n".join(lines)  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, Text, VGroup

        prepare(scene, colors)
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        header = VGroup(*[
            Text(wrap(c, 18), font_size=MIN_FONT_SIZE + 2, color=colors.accent) for c in p.columns  # type: ignore[attr-defined]
        ]).arrange_in_grid(1, len(p.columns), buff=1.2)  # type: ignore[attr-defined]
        body_rows = []
        for row in p.rows:  # type: ignore[attr-defined]
            cells = VGroup(*[
                Text(wrap(c, 18), font_size=MIN_FONT_SIZE, color=colors.text) for c in row
            ]).arrange_in_grid(1, len(row), buff=1.2)
            body_rows.append(cells)
        body = VGroup(*body_rows).arrange(DOWN, buff=0.5)
        group = VGroup(title, header, body).arrange(DOWN, buff=0.5)
        fit(group)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        clock.play(FadeIn(header), run_time=0.6)
        for cells in body_rows:
            clock.play(FadeIn(cells), run_time=0.5)
        clock.finish()

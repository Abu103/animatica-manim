"""Matrix: a grid of numbers with optional cell highlighting.

Made for prompts like "show this matrix" or "multiply these matrices".
Each cell is a rounded rectangle with its value inside; cells can be
highlighted in sequence to walk through an operation.
Duration: 2.0 s + 0.4 s per cell.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit, fit_in_room, prepare, text_card, warn
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_ROWS = 6
MAX_COLS = 6
CELL_SIZE = 0.75
CELL_GAP = 0.12


class Matrix(Component):
    name: ClassVar[str] = "matrix"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        values: list[list[float | int]] = Field(min_length=1, max_length=MAX_ROWS)
        highlight: list[list[int]] = Field(
            default_factory=list,
            description="cells to highlight, each [row, col]",
        )

        @model_validator(mode="after")
        def _check(self):
            if not self.values or not self.values[0]:
                raise ValueError("values must be a non-empty 2D list")
            ncols = len(self.values[0])
            for r, row in enumerate(self.values):
                if len(row) != ncols:
                    raise ValueError(f"row {r} has {len(row)} columns, expected {ncols}")
            if len(self.values) > MAX_ROWS:
                raise ValueError(f"at most {MAX_ROWS} rows")
            if ncols > MAX_COLS:
                raise ValueError(f"at most {MAX_COLS} columns")
            for cell in self.highlight:
                if len(cell) != 2:
                    raise ValueError(f"highlight cell {cell} must be [row, col]")
                r, c = cell
                if not (0 <= r < len(self.values) and 0 <= c < ncols):
                    raise ValueError(f"highlight cell {cell} out of range")
            return self

    def duration(self, p: BaseModel) -> float:
        n = sum(len(r) for r in p.values)  # type: ignore[attr-defined]
        return 2.0 + 0.4 * n

    def fallback_text(self, p: BaseModel) -> str:
        rows = []
        for row in p.values:  # type: ignore[attr-defined]
            rows.append("  ".join(str(v) for v in row))
        return f"{p.title}\n" + "\n".join(rows)  # type: ignore[attr-defined]

    def play(self, scene, p, colors) -> None:
        from manim import (
            DOWN,
            FadeIn,
            Square,
            Text,
            UP,
            VGroup,
        )

        prepare(scene, colors)
        values = p.values  # type: ignore[attr-defined]
        highlight = set(tuple(c) for c in p.highlight)  # type: ignore[attr-defined]
        nrows = len(values)
        ncols = len(values[0])

        title = Text(p.title, font_size=40, color=colors.text).to_edge(UP, buff=0.4)

        cells: list = []
        for r in range(nrows):
            for c in range(ncols):
                v = values[r][c]
                cell = Square(side_length=CELL_SIZE, stroke_width=2, stroke_color=colors.muted)
                cell.set_fill(colors.background, opacity=0)
                cell.move_to(
                    [
                        (c - (ncols - 1) / 2) * (CELL_SIZE + CELL_GAP),
                        -((r - (nrows - 1) / 2) * (CELL_SIZE + CELL_GAP)),
                        0,
                    ]
                )
                label = Text(f"{v:g}", font_size=36, color=colors.text)
                if label.width > CELL_SIZE * 0.85:
                    label.scale_to_fit_width(CELL_SIZE * 0.85)
                label.move_to(cell.get_center())
                group = VGroup(cell, label)
                if (r, c) in highlight:
                    cell.set_fill(colors.accent, opacity=0.35)
                cells.append(group)

        grid = VGroup(*cells).arrange_in_grid(nrows, ncols, buff=CELL_GAP)
        whole = VGroup(title, grid).arrange(DOWN, buff=0.5)
        fit_in_room(scene, whole)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        per = max(0.15, 1.5 / len(cells))
        for cell in cells:
            clock.play(FadeIn(cell), run_time=per)
        clock.finish()

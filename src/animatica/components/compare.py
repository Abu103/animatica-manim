"""Compare: two columns of bullets, fading in alternately. Max 6 bullets per side.

Duration: 2.2 s + 0.6 s per bullet (both sides combined).
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import MIN_FONT_SIZE, Clock, fit, prepare, wrap
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_BULLETS = 6


class Compare(Component):
    name: ClassVar[str] = "compare"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        left: dict
        right: dict

        @model_validator(mode="after")
        def _check(self):
            for side in (self.left, self.right):
                bullets = side.get("bullets") or []
                if not side.get("heading"):
                    raise ValueError("each side needs a 'heading'")
                if not (1 <= len(bullets) <= MAX_BULLETS):
                    raise ValueError(f"bullets must be 1..{MAX_BULLETS}")
            return self

    def duration(self, p: BaseModel) -> float:
        total = len(p.left["bullets"]) + len(p.right["bullets"])  # type: ignore[attr-defined]
        return 2.2 + 0.6 * total

    def fallback_text(self, p: BaseModel) -> str:
        lines = [f"{p.left['heading']}:"]  # type: ignore[attr-defined]
        lines += [f"  - {b}" for b in p.left["bullets"]]  # type: ignore[attr-defined]
        lines.append(f"{p.right['heading']}:")  # type: ignore[attr-defined]
        lines += [f"  - {b}" for b in p.right["bullets"]]  # type: ignore[attr-defined]
        return p.title + ":\n" + "\n".join(lines)  # type: ignore[attr-defined]

    def _build_layout(self, p: BaseModel, colors) -> tuple:
        """Build and position title + left/right columns. No scene calls."""
        from manim import DOWN, LEFT, RIGHT, Text, UP, VGroup
        from manim import config

        def make_column(side: dict, wrap_width: int = 35) -> VGroup:
            head = Text(wrap(str(side["heading"]), 24), font_size=MIN_FONT_SIZE, color=colors.accent)
            bullets = VGroup(*[
                Text(wrap("• " + str(b), wrap_width), font_size=MIN_FONT_SIZE, color=colors.text)
                for b in side["bullets"]
            ]).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
            return VGroup(head, bullets).arrange(DOWN, aligned_edge=LEFT, buff=0.35)

        left = make_column(p.left)
        right = make_column(p.right)

        # Place right column next to left with a horizontal gap
        right.next_to(left, RIGHT, buff=0.8, aligned_edge=UP)

        # Align bullet tops (descenders make heading/bullet bboxes differ between columns)
        right.shift(UP * (left[1].get_top()[1] - right[1].get_top()[1]))

        # Create title to compute its height for max_height
        title = Text(wrap(p.title, 45), font_size=MIN_FONT_SIZE + 8, color=colors.accent)
        # Available height for cols: from just below title to caption band top
        cols_top = config.frame_height / 2 - 0.6 - title.height - 0.5
        caption_band_top = -config.frame_height / 2 + 1.2
        max_height = cols_top - caption_band_top

        # Fit both columns together as one group (shrink only, about group centre)
        cols = VGroup(left, right)
        fit(cols, max_width=config.frame_width - 1.5, max_height=max_height, scale_up=False)

        # Position title at x=0 above columns
        title.to_edge(UP, buff=0.6).set_x(0)

        # Columns below title at x=0
        cols.next_to(title, DOWN, buff=0.5).set_x(0)

        return title, left, right

    def play(self, scene, p, colors) -> None:
        from manim import FadeIn, VGroup, config

        prepare(scene, colors)

        title, left, right = self._build_layout(p, colors)
        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        left_items = [left[0], *left[1]]
        right_items = [right[0], *right[1]]
        li = ri = 0
        while li < len(left_items) or ri < len(right_items):
            if li < len(left_items):
                clock.play(FadeIn(left_items[li]), run_time=0.6)
                li += 1
            if ri < len(right_items):
                clock.play(FadeIn(right_items[ri]), run_time=0.6)
                ri += 1
        clock.finish()

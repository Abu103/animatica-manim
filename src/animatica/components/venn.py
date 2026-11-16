"""Venn diagram: two or three overlapping sets, each with its own items and optional shared regions.

Made for prompts like "venn diagram of even numbers and primes" or "what do dogs, cats and fish share".
`shared` regions name the sets they sit in by index ([0, 1] is where sets 0 and 1 overlap; with three
sets, [0, 1, 2] is the middle). Items are short: 14 characters each, three per region (with three sets: one per shared region of 7 characters, two per set).
Duration: 2.0 s + 0.7 s per set + 0.5 s per shared region.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit_in_room, prepare
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_ITEMS = 3
MAX_ITEM_CHARS = 14
MAX_LABEL = 24


class VennSet(BaseModel):
    label: str = Field(min_length=1, max_length=MAX_LABEL)
    items: list[str] = Field(default_factory=list, max_length=MAX_ITEMS, description="only in this set")

    @model_validator(mode="after")
    def _item_length(self):
        for item in self.items:
            if not item or len(item) > MAX_ITEM_CHARS:
                raise ValueError(f"item {item!r} must be 1-{MAX_ITEM_CHARS} characters")
        return self


class Shared(BaseModel):
    of: list[int] = Field(description="indices of the sets this region is inside, e.g. [0, 1]")
    items: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)

    @model_validator(mode="after")
    def _item_length(self):
        for item in self.items:
            if not item or len(item) > MAX_ITEM_CHARS:
                raise ValueError(f"item {item!r} must be 1-{MAX_ITEM_CHARS} characters")
        return self


class Venn(Component):
    name: ClassVar[str] = "venn"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        sets: list[VennSet] = Field(min_length=2, max_length=3)
        shared: list[Shared] = Field(default_factory=list, max_length=4)

        @model_validator(mode="after")
        def _check(self):
            n = len(self.sets)
            labels = [s.label.strip().lower() for s in self.sets]
            if len(set(labels)) != n:
                raise ValueError("set labels must differ")
            seen: set[tuple[int, ...]] = set()
            for region in self.shared:
                key = tuple(sorted(region.of))
                if len(key) < 2 or len(set(key)) != len(key):
                    raise ValueError(f"shared region {region.of} must name 2 or 3 different sets")
                if any(not 0 <= i < n for i in key):
                    raise ValueError(f"shared region {region.of}: set index out of range for {n} sets")
                if key in seen:
                    raise ValueError(f"shared region {list(key)} is given twice")
                seen.add(key)
            if n == 3:  # three circles leave small regions: the text has to fit them
                if any(len(r.items) > 1 for r in self.shared) or any(len(x.items) > 2 for x in self.sets):
                    raise ValueError("with three sets, give each shared region 1 item and each set at most 2")
                if any(len(item) > 7 for r in self.shared for item in r.items):
                    raise ValueError("with three sets, shared items are at most 7 characters")
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.7 * len(p.sets) + 0.5 * len(p.shared)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [p.title]  # type: ignore[attr-defined]
        for s in p.sets:  # type: ignore[attr-defined]
            lines.append(f"  {s.label}: {', '.join(s.items)}" if s.items else f"  {s.label}")
        for r in p.shared:  # type: ignore[attr-defined]
            names = " + ".join(p.sets[i].label for i in sorted(r.of))  # type: ignore[attr-defined]
            lines.append(f"  {names}: {', '.join(r.items)}" if r.items else f"  {names}")
        return "\n".join(lines)

    def play(self, scene, p, colors) -> None:
        import numpy as np
        from manim import Circle, DOWN, FadeIn, Text, UP, VGroup

        prepare(scene, colors)
        n = len(p.sets)
        k = 1.0 if n == 2 else 0.92  # three circles are taller; shrink them so the text stays large
        radius = 2.0 * k
        shade = [colors.accent, colors.accent2, colors.muted]
        # two sets side by side; three in a triangle (set 0 top-left, 1 top-right, 2 bottom)
        centers = [np.array(c) for c in (
            [(-1.1, 0.0, 0.0), (1.1, 0.0, 0.0)] if n == 2 else
            [(-1.1 * k, 0.7 * k, 0.0), (1.1 * k, 0.7 * k, 0.0), (0.0, -1.2 * k, 0.0)])]

        def lines(items: list[str]):
            col = VGroup(*[Text(t, font_size=32, color=colors.text) for t in items]).arrange(DOWN, buff=0.12)
            return col

        def outward(i: int) -> np.ndarray:
            """Where a set's own items sit: on its far side from the other circle centres."""
            others = np.mean([c for j, c in enumerate(centers) if j != i], axis=0)
            d = centers[i] - others
            return centers[i] + d / (np.linalg.norm(d) or 1.0) * 0.9

        parts: list = []  # what appears together, in order
        for i, s in enumerate(p.sets):
            circle = Circle(radius=radius, stroke_color=shade[i], stroke_width=4).set_fill(shade[i], opacity=0.15)
            circle.move_to(centers[i])
            label = Text(s.label, font_size=32, color=shade[i], weight="BOLD")
            label.next_to(circle, UP if centers[i][1] >= 0 and not (n == 3 and i == 2) else DOWN, buff=0.15)
            group = VGroup(circle, label)
            if s.items:
                group.add(lines(s.items).move_to(outward(i)))
            parts.append(group)
        shared_parts = []
        for r in p.shared:
            if not r.items:
                continue
            idx = sorted(r.of)
            at = np.mean([centers[i] for i in idx], axis=0)
            if n == 3 and len(idx) == 2:  # off the middle, into the part of the lens outside the third circle
                third = centers[({0, 1, 2} - set(idx)).pop()]
                away = at - third
                at = at + away / np.linalg.norm(away) * 0.95 * k
            shared_parts.append(lines(r.items).move_to(at))

        diagram = VGroup(*parts, *shared_parts)
        body = VGroup(Text(p.title, font_size=40, color=colors.text), diagram).arrange(DOWN, buff=0.4)
        fit_in_room(scene, body)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(body[0]), run_time=clock.whole(0.6))
        for g in parts:
            clock.play(FadeIn(g), run_time=clock.whole(0.7))
        for g in shared_parts:
            clock.play(FadeIn(g), run_time=clock.whole(0.5))
        clock.finish()

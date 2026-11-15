"""Probability tree: a root, 1-3 branches, each with up to 3 sub-branches, every edge labelled with its probability.

Made for prompts like "probability tree for two coin flips" or "draw the tree for a medical test".
Sibling probabilities must sum to 1. Every end of the tree shows the probability of its whole path
(the product of the edge probabilities).
Duration: 2.0 s + 0.5 s per node (the branches and sub-branches).
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, model_validator

from animatica.components._draw import Clock, fit_in_room, prepare
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_BRANCHES = 3
MAX_CHILDREN = 3
MAX_LABEL = 40
SUM_TOLERANCE = 0.01


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def _check_sum(items: list, where: str) -> None:
    total = sum(i.p for i in items)
    if abs(total - 1.0) > SUM_TOLERANCE:
        raise ValueError(f"probabilities under {where} sum to {total:.3g}, they must sum to 1")


class Outcome(BaseModel):
    label: str = Field(min_length=1, max_length=MAX_LABEL)
    p: float = Field(gt=0.0, le=1.0, description="probability of this outcome given its parent, 0 < p <= 1")


class Branch(Outcome):
    children: list[Outcome] = Field(default_factory=list, max_length=MAX_CHILDREN)

    @model_validator(mode="after")
    def _children_sum(self):
        if self.children:
            _check_sum(self.children, f"branch {self.label!r}")
        return self


class ProbabilityTree(Component):
    name: ClassVar[str] = "probability_tree"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        root: str = Field(default="Start", min_length=1, max_length=MAX_LABEL)
        branches: list[Branch] = Field(min_length=1, max_length=MAX_BRANCHES)

        @model_validator(mode="after")
        def _branches_sum(self):
            _check_sum(self.branches, "the root")
            return self

    @staticmethod
    def leaves(p: BaseModel) -> list[tuple[str, float]]:
        """Every end of the tree as (path label, probability of the whole path)."""
        out: list[tuple[str, float]] = []
        for b in p.branches:  # type: ignore[attr-defined]
            if not b.children:
                out.append((b.label, b.p))
            for c in b.children:
                out.append((f"{b.label}, {c.label}", b.p * c.p))
        return out

    @staticmethod
    def _node_count(p: BaseModel) -> int:
        return sum(1 + len(b.children) for b in p.branches)  # type: ignore[attr-defined]

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 0.5 * self._node_count(p)

    def fallback_text(self, p: BaseModel) -> str:
        lines = [p.title]  # type: ignore[attr-defined]
        lines += [f"  {path}: {_fmt(prob)}" for path, prob in self.leaves(p)]
        return "\n".join(lines)

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, Line, RIGHT, RoundedRectangle, Text, UP, VGroup

        prepare(scene, colors)

        def node(label: str, color: str):
            text = Text(label, font_size=32, color=colors.text)
            box = RoundedRectangle(corner_radius=0.12, width=text.width + 0.4, height=text.height + 0.3,
                                   stroke_color=color, stroke_width=3)
            return VGroup(box, text)

        def prob_text(x: float, prefix: str = ""):
            return Text(prefix + _fmt(x), font_size=32, color=colors.accent2)

        root = node(p.root, colors.accent)
        level1 = [node(b.label, colors.muted) for b in p.branches]
        level2 = [[node(c.label, colors.muted) for c in b.children] for b in p.branches]

        # columns: each as wide as its widest node, with room between them for the edge's probability
        gap = 2.2
        w1 = max(n.width for n in level1)
        w2 = max((n.width for row in level2 for n in row), default=0.0)
        x1 = root.width / 2 + gap + w1 / 2
        x2 = x1 + w1 / 2 + gap + w2 / 2
        root.move_to([0, 0, 0])

        # rows: one per end of the tree; a parent sits at the mean row of its children
        row_gap = 1.1
        n_rows = sum(max(len(b.children), 1) for b in p.branches)
        y = (n_rows - 1) * row_gap / 2
        steps: list = []  # what appears together: edge, probability, node, path probability
        ends: list = []  # path probabilities in the last column, aligned afterwards
        for bi, b in enumerate(p.branches):
            kids = level2[bi]
            ys = [y - k * row_gap for k in range(max(len(kids), 1))]
            y -= len(ys) * row_gap
            bn = level1[bi].move_to([x1, sum(ys) / len(ys), 0])
            edge = Line(root.get_right(), bn.get_left(), color=colors.muted, stroke_width=3)
            parts = [edge, self._tag(edge, prob_text(b.p), UP, DOWN), bn]
            if not kids:
                parts.append(prob_text(b.p, "= ").next_to(bn, RIGHT, buff=0.3))
            steps.append(VGroup(*parts))
            for ci, c in enumerate(b.children):
                cn = kids[ci].move_to([x2, ys[ci], 0])
                cedge = Line(bn.get_right(), cn.get_left(), color=colors.muted, stroke_width=3)
                cend = prob_text(b.p * c.p, "= ")
                ends.append((cn, cend))
                steps.append(VGroup(cedge, self._tag(cedge, prob_text(c.p), UP, DOWN), cn, cend))
        if ends:  # one column for the path probabilities, not one per node width
            x = max(cn.get_right()[0] for cn, _ in ends) + 0.3
            for cn, cend in ends:
                cend.move_to([x + cend.width / 2, cn.get_center()[1], 0])

        title = Text(p.title, font_size=40, color=colors.text).to_edge(UP, buff=0.4)
        body = VGroup(title, VGroup(root, *steps)).arrange(DOWN, buff=0.5)
        fit_in_room(scene, body)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), FadeIn(root), run_time=clock.whole(0.6))
        for group in steps:
            clock.play(FadeIn(group), run_time=clock.whole(0.5))
        clock.finish()

    @staticmethod
    def _tag(edge, text, up, down):
        """The edge's probability, off the line on the side away from its sibling edges.

        Placed 70% of the way along, where sibling edges have fanned apart, and pushed off the
        line along its normal (not straight up), so a steep edge does not run through its own label.
        """
        import numpy as np

        start, end = edge.get_start(), edge.get_end()
        d = end - start
        norm = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d) or 1.0)  # left of the direction of travel
        going_down = d[1] < -0.05
        want_up = not going_down
        if (norm[1] > 0) != want_up:
            norm = -norm
        return text.move_to(edge.point_from_proportion(0.7) + norm * 0.3)

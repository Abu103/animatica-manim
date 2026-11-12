"""Formula derivation: step-by-step math derivation with highlighted transitions.

Made for prompts like "derive the quadratic formula" or "show how to solve
for x step by step". Each line is an equation; arrows or highlights show
the transition from one step to the next.
Duration: 2.0 s + 1.0 s per step.
"""
from __future__ import annotations

import re
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from animatica.components._draw import SAFE_AREA_MARGIN, Clock, fit, latex_expression, prepare, warn
from animatica.components._draw import caption_band_top as caption_band_top_of
from animatica.components._latex import explain_latex_failure, latex_to_plain
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT
from animatica.storyboard.safety import check_latex

MAX_STEPS = 6

#: Unicode math a model likes to write, and the LaTeX command that typesets it.
_SYMBOLS = {
    "±": r" \pm ", "∓": r" \mp ", "×": r" \times ", "·": r" \cdot ", "÷": r" \div ",
    "≤": r" \le ", "≥": r" \ge ", "≠": r" \ne ", "≈": r" \approx ", "→": r" \to ",
    "⇒": r" \Rightarrow ", "∞": r" \infty ", "π": r" \pi ", "θ": r" \theta ",
    "−": "-", "√": r"\sqrt",
}
_SYMBOL_RE = re.compile("|".join(re.escape(k) for k in _SYMBOLS))

#: ``(a + b) / c`` and ``b/2a``: a fraction whose top is a bracket or a plain
#: token and whose bottom is a plain token. Anything else keeps its slash.
_TOKEN = r"[A-Za-z0-9]+(?:\^\{[^{}]*\})?"
_PAREN_FRAC = re.compile(r"\(([^()]*)\)\s*/\s*(" + _TOKEN + ")")
_TOKEN_FRAC = re.compile(r"(?<![\w}])(" + _TOKEN + r")\s*/\s*(" + _TOKEN + ")")


def step_to_latex(step: str) -> str:
    """One derivation step as LaTeX.

    A step that already is LaTeX (it has a backslash) is used as written.
    Otherwise it is plain math the way a model types it -- ``x^2 + (b/a)x = -c/a``,
    ``sqrt(b^2 - 4ac)``, ``±`` -- and is converted: powers and roots become
    LaTeX, ``a/b`` becomes a stacked fraction, ``±`` becomes ``\\pm``.
    """
    if "\\" in step:
        return step.strip()
    text = _SYMBOL_RE.sub(lambda m: _SYMBOLS[m.group(0)], step)
    text = latex_expression(text)
    previous = None
    while previous != text:  # nested fractions: (a/b) / c
        previous = text
        text = _PAREN_FRAC.sub(lambda m: r"\frac{" + m.group(1) + "}{" + m.group(2) + "}", text)
        text = _TOKEN_FRAC.sub(lambda m: r"\frac{" + m.group(1) + "}{" + m.group(2) + "}", text)
    # A bracket around a stacked fraction has to grow with it.
    return re.sub(r"\(([^()]*\\frac[^()]*)\)", lambda m: r"\left(" + m.group(1) + r"\right)", text)


def is_equation(step: str) -> bool:
    """True when a step is math; a step that is a sentence stays plain text."""
    return "\\" in step or "=" in step or bool(re.search(r"[\^_/±√]|\*\*|\b(?:sqrt|sin|cos|tan|log|ln)\(", step))


class FormulaDerivation(Component):
    name: ClassVar[str] = "formula_derivation"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        steps: list[str] = Field(min_length=1, max_length=MAX_STEPS)
        highlight: list[int] = Field(
            default_factory=list,
            description="step indices to highlight (0-based)",
        )

        @field_validator("steps")
        @classmethod
        def _safe(cls, v: list[str]) -> list[str]:
            for step in v:
                check_latex(step)
            return v

        @model_validator(mode="after")
        def _check_highlight(self) -> "FormulaDerivation.Params":
            n = len(self.steps)
            for i in self.highlight:
                if not (0 <= i < n):
                    raise ValueError(
                        f"highlight index {i} out of range for {n} steps"
                    )
            return self

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 1.0 * len(p.steps)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        lines = [f"{p.title}"] + [f"{i + 1}. {s}" for i, s in enumerate(p.steps)]  # type: ignore[attr-defined]
        return "\n".join(lines)

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, LEFT, FadeIn, MathTex, Text, VGroup

        prepare(scene, colors)
        steps = p.steps  # type: ignore[attr-defined]
        highlight = set(p.highlight)  # type: ignore[attr-defined]
        n = len(steps)

        # The title and the steps live in the space between the top margin and the
        # caption (#29). A two-line caption is taller than a one-line one, so the room
        # is measured from the real caption, not assumed.
        from manim import config

        top = config.frame_height * (0.5 - SAFE_AREA_MARGIN) - 0.3
        band = caption_band_top_of(getattr(scene, "caption_mobject", None))
        max_width = config.frame_width * (1 - 2 * SAFE_AREA_MARGIN) - 0.3
        gap = 0.3

        title = Text(p.title, font_size=34, color=colors.text)
        fit(title, max_width=max_width, max_height=0.8, scale_up=False)

        rendered: list = []
        for i, step in enumerate(steps):
            color = colors.accent if i in highlight else colors.text
            line = None
            if is_equation(step):
                source = step_to_latex(step)
                try:
                    line = MathTex(f"{i + 1}.\\;", source, font_size=48, color=color)
                except Exception as exc:  # LaTeX missing/broken: readable fallback, never abort
                    warn(scene, f"formula_derivation: LaTeX failed for {step!r} ({explain_latex_failure(exc)})")
                    step = latex_to_plain(step)
            if line is None:
                line = Text(f"{i + 1}. {step}", font_size=36, color=color)
            rendered.append(line)

        group = VGroup(*rendered).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        fit(group, max_width=max_width, max_height=top - band - title.height - gap)
        whole = VGroup(title, group).arrange(DOWN, buff=gap)
        whole.move_to([0.0, (top + band) / 2, 0.0])
        title.set_x(0.0)
        group.set_x(0.0)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        per = max(0.3, 1.8 / n)
        for line in rendered:
            clock.play(FadeIn(line), run_time=per)
        clock.finish()

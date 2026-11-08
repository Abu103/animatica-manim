"""Equation: real LaTeX, revealed line by line or transformed step to step. 2.0 s + 2.0 s per extra step."""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from animatica.components._draw import Clock, clear_stage, fit, prepare, warn
from animatica.components._latex import explain_latex_failure, latex_to_markup, latex_to_plain
from animatica.components.base import Component
from animatica.storyboard.safety import check_latex, latex_braces_balanced


class Equation(Component):
    name: ClassVar[str] = "equation"
    # LaTeX is not a hard requirement: _play_without_latex degrades gracefully
    # when LaTeX is unavailable. required_capabilities stays empty.

    class Params(BaseModel):
        mode: Literal["reveal", "transform"] = "reveal"
        latex: list[str] = Field(min_length=1, max_length=6)

        @field_validator("latex")
        @classmethod
        def _safe(cls, v: list[str]) -> list[str]:
            for s in v:
                check_latex(s)
            return v

    def duration(self, p: BaseModel) -> float:
        return 2.0 + 2.0 * (len(p.latex) - 1)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        return "\n".join(latex_to_plain(s) for s in p.latex)  # type: ignore[attr-defined]

    def _play_without_latex(self, scene, p, colors, total: float) -> None:
        """Readable stand-in when LaTeX is unavailable: proper sub/superscripts, one line per equation."""
        from manim import DOWN, FadeIn, MarkupText, VGroup
        clear_stage(scene)
        group = VGroup(*[MarkupText(latex_to_markup(s), font_size=56, color=colors.text) for s in p.latex])
        group.arrange(DOWN, buff=0.6)
        from manim import config
        fit(group, scale_up=False, max_width=config.frame_width * 0.9)
        clock = Clock(scene, total)
        per = max(0.4, (total - 0.8) / len(group))
        for line in group:
            clock.play(FadeIn(line), run_time=min(0.8, per))
        clock.finish()

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, MathTex, ReplacementTransform, TransformMatchingTex, VGroup, Write, config
        prepare(scene, colors)
        total = self.duration(p)
        try:
            for s in p.latex:
                if not latex_braces_balanced(s):
                    raise ValueError("unbalanced braces")
            rendered = [MathTex(s, color=colors.text, font_size=64) for s in p.latex]
        except Exception as exc:  # LaTeX compile failure: degrade, never abort the video
            warn(scene, f"equation: LaTeX failed, showing a simplified rendering instead. {explain_latex_failure(exc)}")
            self._play_without_latex(scene, p, colors, total)
            return
        clock = Clock(scene, total)
        if p.mode == "reveal":
            group = VGroup(*rendered).arrange(DOWN, buff=0.6)
            fit(group, scale_up=False, max_width=config.frame_width * 0.9)
            per = max(0.4, (total - 0.8) / len(rendered))
            for line in group:
                clock.play(Write(line), run_time=min(1.2, per))
        else:
            # Budget: 1.2 + 0.6 + k*(1.2 + 0.4) + closing fade fits inside 2.0 + 2.0*k for every k >= 1.
            current = fit(rendered[0], scale_up=False, max_width=config.frame_width * 0.9)
            clock.play(Write(current), run_time=1.2)
            clock.wait(0.6)
            for nxt in rendered[1:]:
                fit(nxt, scale_up=False, max_width=config.frame_width * 0.9)
                try:
                    clock.play(TransformMatchingTex(current, nxt), run_time=1.2)
                except Exception:
                    clock.play(ReplacementTransform(current, nxt), run_time=1.2)
                current = nxt
                clock.wait(0.4)
        clock.finish()


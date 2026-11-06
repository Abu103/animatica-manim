"""Code walkthrough: step through code lines with a variable panel.

Made for prompts like "walk through this python function line by line".
Shows code with a highlighted current line, plus a panel of variable
name/value pairs that update as execution progresses.
Duration: 3.0 s + 1.0 s per line.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from animatica.components._draw import Clock, fit, prepare, text_card, warn
from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT

MAX_LINES = 12


class CodeWalkthrough(Component):
    name: ClassVar[str] = "code_walkthrough"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        code: str = Field(max_length=MAX_TEXT, description="source code to walk through")
        language: str = Field(default="python", max_length=MAX_TEXT)
        lines: list[int] = Field(
            default_factory=list,
            description="line numbers (1-based) to step through, in order",
        )
        variables: dict[str, str] = Field(
            default_factory=dict,
            description="variable name -> value to show in the panel",
        )

        @property
        def line_count(self) -> int:
            return len(self.code.splitlines())

    def duration(self, p: BaseModel) -> float:
        lines = p.lines or list(range(1, min(p.line_count, MAX_LINES) + 1))  # type: ignore[attr-defined]
        return 3.0 + 1.0 * len(lines)

    def fallback_text(self, p: BaseModel) -> str:
        code_lines = p.code.splitlines()[:MAX_LINES]  # type: ignore[attr-defined]
        shown = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(code_lines))
        var_lines = [f"{k} = {v}" for k, v in p.variables.items()]  # type: ignore[attr-defined]
        return f"{p.title}\n{shown}\n" + "\n".join(var_lines)

    def play(self, scene, p, colors) -> None:
        from manim import DOWN, FadeIn, LEFT, RIGHT, Text, UP, VGroup

        prepare(scene, colors)
        code_lines = p.code.splitlines()[:MAX_LINES]  # type: ignore[attr-defined]
        lines_to_show = p.lines or list(range(1, min(len(code_lines), MAX_LINES) + 1))  # type: ignore[attr-defined]
        variables = p.variables  # type: ignore[attr-defined]

        title = Text(p.title, font_size=40, color=colors.text).to_edge(UP, buff=0.4)
        fit(title)

        # Code lines
        rendered_lines: list = []
        for i, line_text in enumerate(code_lines, 1):
            line = Text(f"{i}: {line_text}", font_size=24, color=colors.muted)
            rendered_lines.append(line)

        code_group = VGroup(*rendered_lines).arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        fit(code_group)

        # Variable panel
        var_entries: list = []
        for var_name, var_value in variables.items():
            entry = Text(f"{var_name} = {var_value}", font_size=24, color=colors.accent)
            var_entries.append(entry)
        var_group = VGroup(*var_entries).arrange(DOWN, buff=0.15, aligned_edge=LEFT) if var_entries else None
        if var_group:
            fit(var_group)

        # Layout: code on left, variables on right
        content = VGroup(code_group, var_group).arrange(RIGHT, buff=1.0) if var_group else code_group
        whole = VGroup(title, content).arrange(DOWN, buff=0.5)
        fit(whole)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        clock.play(FadeIn(code_group), run_time=0.8)
        if var_group:
            clock.play(FadeIn(var_group), run_time=0.6)
        clock.finish()

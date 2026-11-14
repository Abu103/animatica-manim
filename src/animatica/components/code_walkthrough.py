"""Code walkthrough: step through code lines with a variable panel.

Made for prompts like "walk through this python function line by line".
Shows code with line numbers, stepping through selected lines one at a time.
A static variable panel shows name/value pairs (these do not change during
the walkthrough; they provide context for the code being shown).
Duration: 3.0 s + 1.0 s per line stepped through.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from animatica.components._draw import FADE_OUT, Clock, fit, fit_in_room, prepare, unescape_code
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
            description="variable name -> value shown in the static panel",
        )

        _unescape = field_validator("code", mode="before")(unescape_code)

        @model_validator(mode="after")
        def _check(self):
            code_lines = self.code.splitlines()[:MAX_LINES]
            n = len(code_lines)
            for line_num in self.lines:
                if not (1 <= line_num <= n):
                    raise ValueError(
                        f"line {line_num} out of range for code with {n} lines"
                    )
            if len(self.lines) > MAX_LINES:
                raise ValueError(f"at most {MAX_LINES} lines to step through")
            return self

    def duration(self, p: BaseModel) -> float:
        code_lines = p.code.splitlines()[:MAX_LINES]
        lines = p.lines or list(range(1, len(code_lines) + 1))
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
        lines_to_show = p.lines or list(range(1, len(code_lines) + 1))
        variables = p.variables  # type: ignore[attr-defined]

        title = Text(p.title, font_size=40, color=colors.text).to_edge(UP, buff=0.4)
        fit(title)

        # Code lines - all start in muted color
        rendered_lines: list = []
        for i, line_text in enumerate(code_lines, 1):
            line = Text(f"{i}: {line_text}", font_size=24, color=colors.muted)
            rendered_lines.append(line)

        code_group = VGroup(*rendered_lines).arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        fit(code_group)

        # Variable panel (static - values do not change during the walkthrough)
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
        fit_in_room(scene, whole)

        clock = Clock(scene, self.duration(p))
        clock.play(FadeIn(title), run_time=0.6)
        clock.play(FadeIn(code_group), run_time=0.6)
        if var_group:
            clock.play(FadeIn(var_group), run_time=0.6)

        # Step through lines: highlight each one in order with hold time
        n_lines = len(lines_to_show)
        if n_lines > 0:
            # Budget: what is left after the fade-ins and the closing fade-out, in whole video
            # frames (rounded down), so the beat is not longer than the duration it declared.
            left = self.duration(p) - FADE_OUT - clock.used
            hold_time = max(0.2, clock.seconds(int(left / n_lines * clock.fps)))
            for line_num in lines_to_show:
                line_idx = line_num - 1  # convert to 0-based index
                line_mob = rendered_lines[line_idx]
                # Highlight this line by changing its color to accent
                clock.play(line_mob.animate.set_color(colors.accent), run_time=hold_time)

        clock.finish()

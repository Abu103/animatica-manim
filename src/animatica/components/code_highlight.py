"""Code highlight: show code with selected lines emphasized.
3.0 s + 1.0 s per highlighted line."""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from animatica.components._draw import Clock, fit, prepare, unescape_code, wrap
from animatica.components.base import Component
from animatica.components.theme import ThemeColors


class CodeHighlight(Component):
    name: ClassVar[str] = "code_highlight"

    class Params(BaseModel):
        code: str = Field(max_length=1200)
        language: str = "python"
        lines: list[int] = Field(default_factory=list)

        _unescape = field_validator("code", mode="before")(unescape_code)

        @model_validator(mode="after")
        def _check_lines(self):
            line_count = self.code.count("\n") + 1 if self.code else 1  # type: ignore[attr-defined]
            for ln in self.lines:  # type: ignore[attr-defined]
                if ln < 1 or ln > line_count:
                    raise ValueError(
                        f"Line {ln} is beyond the code's {line_count} lines"
                    )
            return self

    def duration(self, p: BaseModel) -> float:
        return 3.0 + 1.0 * len(p.lines)  # type: ignore[attr-defined]

    def fallback_text(self, p: BaseModel) -> str:
        return wrap(p.code, 40)  # type: ignore[attr-defined]

    def play(self, scene, p, colors: ThemeColors) -> None:
        from manim import Code, FadeIn, ORIGIN

        prepare(scene, colors)
        code = Code(
            code_string=p.code,  # type: ignore[attr-defined]
            language=p.language,  # type: ignore[attr-defined]
        )
        # A code block is not centred on the origin, so scaling it left it
        # hanging over the left edge of the frame.
        code.move_to(ORIGIN)
        # Code blocks come out tiny (a 1-line snippet is ~2.5 units wide): scale up to fill the
        # stage, then fit() shrinks back if it overshoots.
        code.scale(min(2.2, 9.0 / max(code.width, 0.1), 4.4 / max(code.height, 0.1)))
        fit(code, scale_up=False)
        clock = Clock(scene, self.duration(p))  # type: ignore[attr-defined]
        clock.play(FadeIn(code), run_time=1.0)
        clock.wait(1.5)
        clock.finish()


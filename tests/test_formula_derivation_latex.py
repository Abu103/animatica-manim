"""formula_derivation sets its steps in LaTeX, not as plain text."""
from __future__ import annotations

import pytest

from animatica.components.formula_derivation import FormulaDerivation, is_equation, step_to_latex
from animatica.storyboard.safety import UnsafeInput


@pytest.mark.parametrize(
    ("plain", "latex"),
    [
        ("ax^2 + bx + c = 0", "ax^{2} + bx + c = 0"),
        ("x^2 + (b/a)x = -c/a", r"x^{2} + \left(\frac{b}{a}\right)x = -\frac{c}{a}"),
        ("(x + b/2a)^2 = (b^2 - 4ac) / 4a^2", r"\left(x + \frac{b}{2a}\right)^{2} = \frac{b^{2} - 4ac}{4a^{2}}"),
        ("x = (-b ± sqrt(b^2 - 4ac)) / 2a", r"x = \frac{-b \pm \sqrt{b^{2} - 4ac}}{2a}"),
        ("a ≤ b", r"a \le b"),
    ],
)
def test_plain_math_becomes_latex(plain: str, latex: str):
    assert " ".join(step_to_latex(plain).split()) == latex


def test_a_step_that_is_already_latex_is_kept():
    step = r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}"
    assert step_to_latex(step) == step


def test_sentences_stay_plain_text_and_equations_are_math():
    assert not is_equation("Subtract three from both sides")
    assert is_equation("x + 3 = 7")
    assert is_equation(r"\frac{a}{b}")


def test_blocked_latex_commands_are_rejected():
    with pytest.raises((UnsafeInput, ValueError)):
        FormulaDerivation.Params.model_validate({"title": "t", "steps": [r"\input{/etc/passwd}"]})

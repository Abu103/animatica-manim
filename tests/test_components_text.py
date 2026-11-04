import pytest
from pydantic import ValidationError

from animatica.components.equation import Equation
from animatica.components.steps_list import StepsList
from animatica.components.title_card import TitleCard


def test_durations_follow_formulas():
    assert TitleCard().duration(TitleCard.Params(title="T")) == 3.0
    eq = Equation()
    assert eq.duration(Equation.Params(latex=["a"])) == 2.0
    assert eq.duration(Equation.Params(latex=["a", "b", "c"])) == 6.0
    sl = StepsList()
    assert sl.duration(StepsList.Params(items=["a", "b"])) == 4.0
    assert sl.duration(StepsList.Params(items=["a"] * 8)) == 13.0


def test_equation_rejects_unsafe_latex():
    with pytest.raises(ValidationError):
        Equation.Params(latex=[r"\write18{rm -rf}"])


def test_equation_rejects_empty_and_too_many():
    with pytest.raises(ValidationError):
        Equation.Params(latex=[])
    with pytest.raises(ValidationError):
        Equation.Params(latex=["a"] * 7)


def test_steps_and_title_limits():
    with pytest.raises(ValidationError):
        StepsList.Params(items=[])
    with pytest.raises(ValidationError):
        StepsList.Params(items=["a"] * 9)
    with pytest.raises(ValidationError):
        TitleCard.Params(title="x" * 301)


def test_fallback_text():
    assert "Hello" in TitleCard().fallback_text(TitleCard.Params(title="Hello"))
    assert "a^2" in Equation().fallback_text(Equation.Params(latex=["a^2"]))
    assert "one" in StepsList().fallback_text(StepsList.Params(items=["one", "two"]))


@pytest.mark.render
def test_title_card_plays(run_component):
    s, warnings = run_component(TitleCard(), TitleCard.Params(title="Hello", subtitle="World"))
    assert s.renderer.num_plays >= 1 and warnings == []


@pytest.mark.render
@pytest.mark.parametrize("mode", ["reveal", "transform"])
def test_equation_plays(run_component, mode):
    s, warnings = run_component(Equation(), Equation.Params(mode=mode, latex=["a^2+b^2=c^2", "c=\\sqrt{a^2+b^2}"]))
    assert s.renderer.num_plays >= 1 and warnings == []


@pytest.mark.render
def test_equation_bad_latex_degrades_with_warning(run_component):
    s, warnings = run_component(Equation(), Equation.Params(latex=[r"\frac{a}{"]))
    assert s.renderer.num_plays >= 1
    assert len(warnings) == 1 and "equation" in warnings[0]


@pytest.mark.render
def test_steps_list_plays(run_component):
    s, warnings = run_component(StepsList(), StepsList.Params(items=["First", "Second", "Third"]))
    assert s.renderer.num_plays >= 1 and warnings == []


def test_wrap_keeps_explicit_line_breaks():
    from animatica.components._draw import wrap
    assert wrap("F_0 = 0\nF_1 = 1", 40) == "F_0 = 0\nF_1 = 1"
    assert wrap("a " * 30, 20).count("\n") >= 2


import pytest

from animatica.components.formula_derivation import FormulaDerivation
from animatica.components.registry import default_registry


def test_registered():
    assert "formula_derivation" in default_registry().names()


def test_duration_is_2s_plus_1s_per_step():
    p = FormulaDerivation.Params(title="t", steps=["a = b", "b = c"])
    assert FormulaDerivation().duration(p) == pytest.approx(2.0 + 1.0 * 2)


def test_rejects_too_many_steps():
    with pytest.raises(Exception):
        FormulaDerivation.Params(title="t", steps=["s"] * 7)


def test_rejects_empty_steps():
    with pytest.raises(Exception):
        FormulaDerivation.Params(title="t", steps=[])


def test_rejects_bad_highlight():
    with pytest.raises(Exception):
        FormulaDerivation.Params(
            title="t",
            steps=["a = b"],
            highlight=[5],  # out of range
        )


def test_fallback_text_contains_steps():
    p = FormulaDerivation.Params(title="Derivation", steps=["x = 5", "x + 1 = 6"])
    text = FormulaDerivation().fallback_text(p)
    assert "Derivation" in text
    assert "x = 5" in text
    assert "x + 1 = 6" in text


def test_highlight_within_range_is_ok():
    p = FormulaDerivation.Params(
        title="t",
        steps=["a = b", "b = c"],
        highlight=[0, 1],
    )
    assert FormulaDerivation().duration(p) == pytest.approx(4.0)

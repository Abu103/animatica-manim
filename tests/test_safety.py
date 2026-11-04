import math

import pytest

from animatica.storyboard.safety import UnsafeInput, check_latex, parse_function


def test_good_latex_passes():
    check_latex(r"a^2+b^2=c^2")
    check_latex(r"\frac{a}{b} + \sqrt{x}")


@pytest.mark.parametrize("seq", [r"\write18", r"\input", r"\include", r"\openin", r"\openout", r"\immediate", r"\catcode"])
def test_denylisted_sequences_raise(seq):
    with pytest.raises(UnsafeInput):
        check_latex(f"a {seq}{{x}} b")


def test_latex_over_max_text_raises():
    with pytest.raises(UnsafeInput):
        check_latex("x" * 301)


def test_parse_function_values():
    assert parse_function("sin(x)^2 + 1/2")(0.0) == 0.5
    assert parse_function("x^2")(3) == 9
    assert parse_function("-x^2")(3) == -9
    assert parse_function("2*pi")(0) == pytest.approx(2 * math.pi)
    assert parse_function("exp(0) + abs(-2) + sqrt(4)")(0) == 5


@pytest.mark.parametrize("bad", ["__import__('os')", "x.real", "open('f')", "2x", "lambda: 1", "x if x else 1",
                                 "[1,2]", "'a'", "sin(x, 2)", "True", "1j"])
def test_parse_function_rejects(bad):
    with pytest.raises(UnsafeInput):
        parse_function(bad)


def test_domain_errors_give_nan():
    assert math.isnan(parse_function("1/x")(0))
    assert math.isnan(parse_function("log(x)")(-1))
    assert math.isnan(parse_function("sqrt(x)")(-1))
    assert math.isnan(parse_function("x^x^x^x")(1e6))


def test_overlong_expression_rejected():
    with pytest.raises(UnsafeInput):
        parse_function("x+" * 200 + "x")


from animatica.storyboard.safety import latex_braces_balanced


@pytest.mark.parametrize("s,ok", [
    (r"\frac{a}{b}", True), (r"\frac{a}{", False), ("a}", False), ("{", False),
    (r"\{ x \}", True), (r"\left\{ x", True), ("{{a}{b}}", True), ("", True),
])
def test_latex_braces_balanced(s, ok):
    assert latex_braces_balanced(s) is ok


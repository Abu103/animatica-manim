import pytest

from animatica.components.matrix import Matrix
from animatica.components.registry import default_registry


def test_registered():
    assert "matrix" in default_registry().names()


def test_duration_is_2s_plus_0_4_per_cell():
    p = Matrix.Params(title="t", values=[[1, 2], [3, 4]])
    assert Matrix().duration(p) == pytest.approx(2.0 + 0.4 * 4)


def test_rejects_irregular_rows():
    with pytest.raises(Exception):
        Matrix.Params(title="t", values=[[1, 2], [3]])


def test_rejects_too_many_rows():
    with pytest.raises(Exception):
        Matrix.Params(title="t", values=[[1]] * 7)


def test_rejects_too_many_cols():
    with pytest.raises(Exception):
        Matrix.Params(title="t", values=[[1] * 7])


def test_rejects_bad_highlight():
    with pytest.raises(Exception):
        Matrix.Params(
            title="t",
            values=[[1, 2], [3, 4]],
            highlight=[[5, 0]],  # row 5 out of range
        )


def test_fallback_text_contains_values():
    p = Matrix.Params(title="Demo", values=[[1, 2], [3, 4]])
    text = Matrix().fallback_text(p)
    assert "1" in text and "2" in text and "3" in text and "4" in text


def test_highlight_within_range_is_ok():
    p = Matrix.Params(
        title="t",
        values=[[1, 2], [3, 4]],
        highlight=[[0, 0], [1, 1]],
    )
    assert Matrix().duration(p) == pytest.approx(2.0 + 0.4 * 4)

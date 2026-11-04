import pytest

from animatica.components.registry import default_registry
from animatica.components.table import Table


def test_registered():
    assert "table" in default_registry().names()


def test_duration_is_2s_plus_0_5_per_row():
    p = Table.Params(title="t", columns=["a", "b"], rows=[["1", "2"], ["3", "4"]])
    assert Table().duration(p) == pytest.approx(2.0 + 0.5 * 2)


@pytest.mark.parametrize("bad", [
    {"title": "t", "columns": ["a", "b"], "rows": [["1"]]},                 # ragged row
    {"title": "t", "columns": ["a"], "rows": [["x"]] * 7},                  # too many rows
    {"title": "t", "columns": ["a"] * 7, "rows": [["x"] * 7]},              # too many cols
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        Table.Params(**bad)


def test_fallback_text_is_plain_table():
    p = Table.Params(title="Demo", columns=["a", "b"], rows=[["1", "2"]])
    t = Table().fallback_text(p)
    assert "a | b" in t and "1 | 2" in t

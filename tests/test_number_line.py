import pytest

from animatica.components.number_line import NumberLine
from animatica.components.registry import default_registry


def test_registered():
    assert "number_line" in default_registry().names()


def test_duration_is_2s_plus_0_7_per_jump():
    p = NumberLine.Params(title="t", start=0, end=10, jumps=[(0, 3), (3, 7)])
    assert NumberLine().duration(p) == pytest.approx(2.0 + 0.7 * 2)


@pytest.mark.parametrize("bad", [
    {"title": "t", "start": 10, "end": 0},                    # end <= start
    {"title": "t", "start": 0, "end": 10, "marks": [11]},      # mark out of range
    {"title": "t", "start": 0, "end": 10, "jumps": [(-1, 5)]}, # jump out of range
])
def test_rejects_bad_params(bad):
    with pytest.raises(Exception):
        NumberLine.Params(**bad)


def test_fallback_text_mentions_jumps():
    p = NumberLine.Params(title="Demo", start=0, end=10, jumps=[(0, 5)])
    assert "0 -> 5" in NumberLine().fallback_text(p)

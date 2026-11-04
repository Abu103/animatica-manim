import pytest

from animatica.components._scale import resolve_scale, scaled_heights
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Storyboard

FIB = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610]


def test_auto_scale_linear_for_even_values():
    assert resolve_scale([3, 5, 2, 7]) == "linear"


def test_auto_scale_sqrt_for_fibonacci():
    assert resolve_scale(FIB) == "sqrt"


def test_auto_scale_log_for_huge_spread():
    assert resolve_scale([1, 1, 2, 3, 5, 1000000]) == "log"


def test_explicit_scale_wins():
    assert resolve_scale(FIB, "linear") == "linear"


def test_heights_have_minimum_and_max_equals_cap():
    h, used = scaled_heights(FIB, 3.0, 0.12)
    assert used == "sqrt" and min(h) >= 0.12 and h[-1] == pytest.approx(3.0)
    assert h == sorted(h)  # monotonic for sorted input


def test_all_zero_values_do_not_divide_by_zero():
    h, _ = scaled_heights([0, 0, 0], 3.0, 0.12)
    assert h == [0.12, 0.12, 0.12]


def _sb(scenes):
    return Storyboard.model_validate({"version": "1", "title": "t", "scenes": [{"beats": [b]} for b in scenes]})


def _bounce(values, labels=None, title="x"):
    p = {"title": title, "values": values}
    if labels:
        p["labels"] = labels
    return {"component": "bounce_sequence", "params": p, "caption": "c"}


def test_lint_merges_split_sequence_and_drops_repeat_chart():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Fib"}, "caption": "a"},
        _bounce(FIB[:12]),
        {"component": "equation", "params": {"mode": "reveal", "latex": ["F_0=0"]}, "caption": "e"},
        _bounce(FIB[12:], ["12", "13", "14", "15"]),
        {"component": "bar_chart", "params": {"title": "g", "labels": ["0", "5"], "values": [0, 5]}, "caption": "b"},
    ])
    out, notes = lint_storyboard(sb)
    comps = [s.beats[0].component for s in out.scenes]
    assert comps == ["title_card", "bounce_sequence", "equation"]
    assert out.scenes[1].beats[0].params["values"] == FIB
    assert len(notes) == 2


def test_lint_is_idempotent_and_leaves_clean_storyboards_alone():
    sb = _sb([{"component": "title_card", "params": {"title": "Fib"}, "caption": "a"}, _bounce(FIB[:5])])
    out, notes = lint_storyboard(sb)
    assert out is sb and notes == []


def test_lint_does_not_merge_past_the_cap():
    sb = _sb([_bounce(list(range(15))), _bounce(list(range(10)))])
    out, _ = lint_storyboard(sb)
    assert len(out.scenes) == 2


def test_lint_warns_about_phantom_ball():
    sb = _sb([{"component": "title_card", "params": {"title": "Fib"}, "caption": "Watch the ball bounce"}])
    _, notes = lint_storyboard(sb)
    assert any("ball" in n for n in notes)


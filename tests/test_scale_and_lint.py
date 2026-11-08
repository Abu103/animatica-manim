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
        {"component": "equation", "params": {"mode": "reveal", "latex": ["F_0=0"]}, "caption": "e"},
        _bounce(FIB[:12]),
        _bounce(FIB[12:], ["12", "13", "14", "15"]),
        {"component": "bar_chart", "params": {"title": "g", "labels": ["0", "5"], "values": [0, 5]}, "caption": "b"},
    ])
    out, notes = lint_storyboard(sb)
    comps = [s.beats[0].component for s in out.scenes]
    assert comps == ["title_card", "equation", "bounce_sequence"]
    assert out.scenes[2].beats[0].params["values"] == FIB
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


def test_lint_warns_when_not_opened_by_title_card():
    sb = _sb([
        _bounce(FIB[:5]),
        {"component": "equation", "params": {"mode": "reveal", "latex": ["F_0=0"]}, "caption": "e"},
    ])
    _, notes = lint_storyboard(sb)
    assert any("open with a title_card" in n for n in notes)


def test_lint_warns_on_narrative_regression():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Fib"}, "caption": "a"},
        _bounce(FIB[:5]),
        {"component": "equation", "params": {"mode": "reveal", "latex": ["F_0=0"]}, "caption": "e"},
    ])
    _, notes = lint_storyboard(sb)
    assert any("moves backward" in n for n in notes)


def test_lint_allows_closing_title_as_summary():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Fib"}, "caption": "a"},
        _bounce(FIB[:5]),
        {"component": "title_card", "params": {"title": "The End"}, "caption": "done"},
    ])
    _, notes = lint_storyboard(sb)
    assert not any("moves backward" in n for n in notes)


def test_lint_clean_arc_produces_no_order_notes():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Fib"}, "caption": "a"},
        {"component": "equation", "params": {"mode": "reveal", "latex": ["F_0=0"]}, "caption": "e"},
        _bounce(FIB[:5]),
    ])
    _, notes = lint_storyboard(sb)
    assert not any("title_card" in n or "backward" in n for n in notes)


def test_lint_single_scene_needs_no_title_card():
    # P0 acceptance: "one scene, ... no warnings". A lone demo scene has no
    # ordering to violate, so it must not be told to open with a title_card.
    sb = _sb([_bounce(FIB[:5])])
    _, notes = lint_storyboard(sb)
    assert not any("title_card" in n for n in notes)
    assert not any("backward" in n for n in notes)


def test_lint_compare_is_demo_not_summary():
    # compare is a two-column demo, not a summary. A graph after compare is
    # the same stage, so no "moves backward" warning.
    sb = _sb([
        {"component": "title_card", "params": {"title": "C"}, "caption": "a"},
        {"component": "compare", "params": {"title": "c", "left": {"heading": "L", "bullets": ["a"]}, "right": {"heading": "R", "bullets": ["b"]}}, "caption": "b"},
        {"component": "graph", "params": {"fn": "sin(x)", "x_range": [-3, 3], "y_range": [-2, 2]}, "caption": "c"},
    ])
    _, notes = lint_storyboard(sb)
    assert not any("moves backward" in n for n in notes)


def test_lint_unknown_component_does_not_create_false_regression():
    # Unclassified components are neutral: they neither trigger nor suppress
    # a regression warning. bounce(stage 2) -> unknown -> graph(stage 2) is clean.
    sb = _sb([
        {"component": "title_card", "params": {"title": "x"}, "caption": "a"},
        _bounce(FIB[:5]),
        {"component": "made_up_component", "params": {}, "caption": "u"},
        {"component": "graph", "params": {"fn": "sin(x)", "x_range": [-3, 3], "y_range": [-2, 2]}, "caption": "c"},
    ])
    _, notes = lint_storyboard(sb)
    assert not any("moves backward" in n for n in notes)


def test_lint_unknown_component_does_not_mask_regression():
    # Unclassified components are skipped, so a real regression is still reported.
    # bounce(stage 2) -> unknown -> equation(stage 1) flags equation.
    sb = _sb([
        {"component": "title_card", "params": {"title": "x"}, "caption": "a"},
        _bounce(FIB[:5]),
        {"component": "made_up_component", "params": {}, "caption": "u"},
        {"component": "equation", "params": {"mode": "reveal", "latex": ["F_0=0"]}, "caption": "e"},
    ])
    _, notes = lint_storyboard(sb)
    assert any("moves backward" in n for n in notes)


# ---------------------------------------------------------------------------
# Closing summary recognition
# ---------------------------------------------------------------------------

def test_lint_closing_steps_list_is_summary_not_regression():
    # A steps_list at the end, after demo content (graph stage 2), is a
    # closing summary: title -> definition -> demo -> summary. No warning.
    sb = _sb([
        {"component": "title_card", "params": {"title": "Taylor"}, "caption": "a"},
        {"component": "equation", "params": {"mode": "reveal", "latex": ["e^x"]}, "caption": "d"},
        {"component": "graph", "params": {"fn": "exp(x)", "x_range": [-2, 2], "y_range": [0, 4]}, "caption": "m"},
        {"component": "steps_list", "params": {"items": ["more terms help", "convergence has limits"]}, "caption": "s"},
    ])
    _, notes = lint_storyboard(sb)
    assert not any("moves backward" in n for n in notes), f"unexpected notes: {notes}"


def test_lint_closing_table_is_summary_not_regression():
    # A table at the end, after demo content, is a closing summary.
    sb = _sb([
        {"component": "title_card", "params": {"title": "Data"}, "caption": "a"},
        {"component": "graph", "params": {"fn": "sin(x)", "x_range": [-3, 3], "y_range": [-2, 2]}, "caption": "m"},
        {"component": "table", "params": {"columns": ["x", "y"], "rows": [["0", "0"]]}, "caption": "s"},
    ])
    _, notes = lint_storyboard(sb)
    assert not any("moves backward" in n for n in notes), f"unexpected notes: {notes}"


def test_lint_steps_list_in_middle_after_demo_still_regresses():
    # A steps_list in the MIDDLE (between demo and equation) is still a
    # real regression: demo(stage 2) -> steps_list(stage 1) moves backward.
    sb = _sb([
        {"component": "title_card", "params": {"title": "Taylor"}, "caption": "a"},
        {"component": "graph", "params": {"fn": "exp(x)", "x_range": [-2, 2], "y_range": [0, 4]}, "caption": "m"},
        {"component": "steps_list", "params": {"items": ["takeaways"]}, "caption": "s"},
        {"component": "equation", "params": {"mode": "reveal", "latex": ["e^x"]}, "caption": "d"},
    ])
    _, notes = lint_storyboard(sb)
    assert any("moves backward" in n for n in notes), f"expected regression warning, got: {notes}"


def test_lint_steps_list_at_end_without_demo_is_clean():
    # title_card(stage 0) -> steps_list(stage 1) at the end: forward, no warning.
    # steps_list is not a summary here because no demo preceded it.
    sb = _sb([
        {"component": "title_card", "params": {"title": "How To"}, "caption": "a"},
        {"component": "steps_list", "params": {"items": ["step 1", "step 2"]}, "caption": "s"},
    ])
    _, notes = lint_storyboard(sb)
    assert not any("moves backward" in n for n in notes), f"unexpected notes: {notes}"


def test_lint_closing_steps_list_after_only_definition_is_clean():
    # equation(stage 1) -> steps_list(stage 1) at the end: same stage, no warning.
    sb = _sb([
        {"component": "title_card", "params": {"title": "Math"}, "caption": "a"},
        {"component": "equation", "params": {"mode": "reveal", "latex": ["a^2"]}, "caption": "d"},
        {"component": "steps_list", "params": {"items": ["takeaway"]}, "caption": "s"},
    ])
    _, notes = lint_storyboard(sb)
    assert not any("moves backward" in n for n in notes), f"unexpected notes: {notes}"


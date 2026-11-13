"""Tests for the generation guidance module."""
from __future__ import annotations

from animatica.ai.guidance import check_generation_guidance
from animatica.storyboard.models import Storyboard


def _sb(scenes):
    return Storyboard.model_validate(
        {"version": "1", "title": "t", "scenes": [{"beats": [b]} for b in scenes]}
    )


def test_clean_storyboard_no_guidance_notes():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Taylor"}, "caption": "Taylor series approximate smooth functions with polynomials."},
        {"component": "equation", "params": {"mode": "reveal", "latex": ["e^x"]}, "caption": "Every derivative of e^x equals 1, giving this expansion."},
        {"component": "graph", "params": {"fn": "exp(x)", "approx_fn": "1 + x + x**2/2", "x_range": [-2, 2], "y_range": [0, 4]}, "caption": "The parabola approximates e^x near zero; more terms improve the match."},
        {"component": "steps_list", "params": {"items": ["More terms help near the center.", "Convergence has a limited radius."]}, "caption": "Key takeaways for using Taylor series in practice."},
    ])
    notes = check_generation_guidance(sb)
    assert notes == [], f"expected no guidance notes, got: {notes}"


def test_caption_describing_production_mechanics_is_flagged():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Taylor"}, "caption": "A title card introducing Taylor series."},
    ])
    notes = check_generation_guidance(sb)
    assert any("production mechanics" in n for n in notes), f"expected flag, got: {notes}"
    assert any("title card" in n for n in notes), f"expected 'title card' flag, got: {notes}"


def test_comparison_without_visual_is_flagged():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Taylor"}, "caption": "Taylor series approximate e^x."},
        {"component": "graph", "params": {"fn": "exp(x)", "x_range": [-2, 2], "y_range": [0, 4]}, "caption": "The approximation compares to the original function."},
    ])
    notes = check_generation_guidance(sb)
    assert any("visual comparison" in n for n in notes), f"expected flag, got: {notes}"


def test_comparison_with_approx_fn_is_clean():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Taylor"}, "caption": "Taylor series approximate e^x."},
        {"component": "graph", "params": {"fn": "exp(x)", "approx_fn": "1 + x", "x_range": [-2, 2], "y_range": [0, 4]}, "caption": "The line approximates e^x near zero."},
    ])
    notes = check_generation_guidance(sb)
    assert not any("visual comparison" in n for n in notes), f"unexpected notes: {notes}"


def test_comparison_with_bar_chart_is_clean():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Options"}, "caption": "Compare option A versus option B."},
        {"component": "bar_chart", "params": {"title": "Choice", "labels": ["A", "B"], "values": [5, 7]}, "caption": "Option B scores higher."},
    ])
    notes = check_generation_guidance(sb)
    assert not any("visual comparison" in n for n in notes), f"unexpected notes: {notes}"


def test_empty_caption_not_flagged():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Taylor"}, "caption": ""},
    ])
    notes = check_generation_guidance(sb)
    assert notes == [], f"expected no notes, got: {notes}"


def test_the_word_before_alone_is_not_a_comparison():
    """fibonacci.json: 'the sum of the two before it' was flagged as a comparison."""
    sb = _sb([{"component": "title_card", "params": {"title": "Fib"}, "caption": "Each number is the sum of the two before it."}])
    assert check_generation_guidance(sb) == []


def test_before_and_after_without_a_visual_is_still_flagged():
    sb = _sb([{"component": "title_card", "params": {"title": "Fix"}, "caption": "Look at the before and after."}])
    assert any("visual comparison" in n for n in check_generation_guidance(sb))


def test_comparison_words_match_whole_words_only():
    sb = _sb([{"component": "title_card", "params": {"title": "T"}, "caption": "Beforehand, prepare the originality check."}])
    assert check_generation_guidance(sb) == []


def test_stat_callout_delta_counts_as_a_visual_comparison():
    """stat_callout.json: a delta of '+12% vs last year' is drawn next to the number."""
    sb = _sb([{"component": "stat_callout", "params": {"value": "98%", "label": "pass rate", "delta": "+12% vs last year"},
               "caption": "Nearly all students pass, up 12% from last year."}])
    assert check_generation_guidance(sb) == []


def test_stat_callout_without_a_delta_does_not_hide_a_missing_comparison():
    sb = _sb([{"component": "stat_callout", "params": {"value": "98%", "label": "pass rate vs the original goal"},
               "caption": "Nearly all students pass."}])
    assert any("visual comparison" in n for n in check_generation_guidance(sb))

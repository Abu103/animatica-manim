"""N3 (F6): magnitude phrasing names a signed change, not an absolute value.

"fell by 4" / "down 4" over a param of -4 is grounded. The sign
relaxation applies only to a number immediately preceded by a decrease
phrase; positive-vs-negative matching stays strict everywhere else.
"""
from __future__ import annotations

import pytest

from animatica.components.registry import default_registry
from animatica.storyboard.models import Beat, Scene, Storyboard
from animatica.verify.numbers import check_numbers


def _sb(caption="", narration=""):
    return Storyboard(title="t", scenes=[Scene(beats=[Beat(
        component="stat_callout", params={"value": "-4", "label": "change"},
        caption=caption, narration=narration,
    )])])


def _findings(sb):
    return check_numbers(sb, default_registry())


def test_fell_by_four_grounds_a_negative_param():
    assert _findings(_sb(caption="the value fell by 4 points")) == []


def test_down_four_grounds_a_negative_param_in_narration():
    assert _findings(_sb(narration="it was down 4 compared with last year")) == []


def test_dropped_by_and_word_number_ground():
    assert _findings(_sb(caption="it dropped by 4")) == []
    assert _findings(_sb(caption="it decreased by four points")) == []


def test_positive_phrasing_does_not_accept_a_negative_param():
    findings = _findings(_sb(caption="the value grew by 4 points"))
    assert len(findings) == 1 and "4" in findings[0].message


def test_negative_param_does_not_ground_a_plain_number():
    findings = _findings(_sb(caption="the reading is 4"))
    assert len(findings) == 1


def test_decrease_phrasing_does_not_accept_a_positive_param():
    sb = Storyboard(title="t", scenes=[Scene(beats=[Beat(
        component="stat_callout", params={"value": "4", "label": "change"},
        caption="the value fell by 4 points",
    )])])
    findings = _findings(sb)
    assert len(findings) == 1


def test_other_numbers_in_the_same_sentence_stay_strict():
    sb = Storyboard(title="t", scenes=[Scene(beats=[Beat(
        component="stat_callout", params={"value": "-4", "label": "change"},
        caption="it fell by 4, then settled at 4",
    )])])
    findings = _findings(sb)
    assert len(findings) == 1 and "4" in findings[0].message


@pytest.mark.parametrize("caption", ["it fell sharply by 4", "there was a drop of 4"])
def test_adverb_and_drop_of_phrases_ground_a_signed_param(caption):
    assert _findings(_sb(caption=caption)) == []


def test_breakdown_is_not_a_decrease_phrase():
    # "down" inside "breakdown" is part of a word, not phrasing.
    findings = _findings(_sb(caption="the breakdown 4 is shown"))
    assert len(findings) == 1

"""N5: param-vs-claim checks for bounce_sequence spikes and graph labels.

(a) "the fourth and eighth terms spike" over values must name the largest
    entries (1-based ordinals -> 0-based indices 3 and 7).
(b) a graph labelled "Cost per append" whose fn is a plain identity line
    draws no cost data: warn.
Both are warn-only, and neither guesses on unrelated wording.
"""
from __future__ import annotations

import pytest

from animatica.components.registry import default_registry
from animatica.storyboard.models import Beat, Scene, Storyboard
from animatica.verify.claims import check_claims, unchecked_sentences

BOUNCE = [1, 1, 1, 2, 1, 1, 1, 4, 1, 1]  # out-8/v1 fixture


def _sb(component, params, caption="", narration=""):
    return Storyboard(title="t", scenes=[Scene(beats=[
        Beat(component=component, params=params, caption=caption, narration=narration)
    ])])


def _bounce(caption="", narration=""):
    return _sb("bounce_sequence", {"title": "t", "values": BOUNCE},
               caption=caption, narration=narration)


def _graph(fn="x", label="Cost per append"):
    return _sb("graph", {"fn": fn, "x_range": [0, 10], "y_range": [0, 10],
                         "label": label},
               caption="a plotted line")


def _findings(sb):
    return check_claims(sb, default_registry())


def test_correct_spike_ordinals_do_not_warn():
    # 4th -> index 3 (value 2), 8th -> index 7 (value 4): the two largest.
    assert _findings(_bounce(caption="The fourth and eighth terms spike.")) == []


def test_wrong_spike_ordinals_warn():
    findings = _findings(_bounce(caption="The second and fifth terms spike."))
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "second" in findings[0].message.lower()


def test_digit_ordinals_and_narration_are_checked():
    assert _findings(_bounce(narration="the 4th and 8th terms jump")) == []
    findings = _findings(_bounce(narration="the 2nd and 5th terms jump"))
    assert len(findings) == 1 and findings[0].field == "narration"


def test_spike_word_is_required():
    # Naming terms without a spike claim asserts nothing about magnitude.
    assert _findings(_bounce(caption="The fourth and eighth terms are shown.")) == []


@pytest.mark.parametrize("fn", ["x", "x+0", "0+x", "x-0", "x/1", "1*x", "x*1"])
def test_identity_line_with_a_cost_label_warns(fn):
    findings = _findings(_graph(fn=fn))
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "identity" in findings[0].message.lower()


def test_per_append_phrase_also_triggers():
    findings = _findings(_graph(label="Operations per append"))
    assert len(findings) == 1


def test_real_function_with_a_cost_label_does_not_warn():
    assert _findings(_graph(fn="x**2")) == []
    assert _findings(_graph(fn="x*log(x)")) == []


def test_identity_without_a_cost_label_does_not_warn():
    assert _findings(_graph(label="Input value")) == []


def test_param_claim_sentences_are_not_listed_as_unchecked():
    for sb in [_bounce(caption="The second and fifth terms spike."), _graph()]:
        sentences = [s for _, s in unchecked_sentences(sb, default_registry())]
        assert not any("Cost per append" in s or "spike" in s for s in sentences)


def test_unrelated_ordinal_in_another_clause_is_ignored():
    # "first section" is not a spike claim; only ordinals in the clause
    # that actually mentions spiking are checked.
    sb = _bounce(caption="The first section sets up the problem; the eighth term spikes.")
    assert _findings(sb) == []


@pytest.mark.parametrize("fn", ["1.0*x", "(x)", "x + 0.0"])
def test_more_identity_spellings_warn(fn):
    findings = _findings(_graph(fn=fn))
    assert len(findings) == 1 and findings[0].severity == "warn"


def test_correct_param_claims_still_count_as_checked():
    from animatica.verify.claims import scan_claims

    checked, findings = scan_claims(_bounce(caption="The fourth and eighth terms spike."),
                                    default_registry())
    assert findings == []
    assert checked >= 1
    checked, findings = scan_claims(_graph(), default_registry())
    assert len(findings) == 1  # cost label over an identity line warns
    assert checked >= 1

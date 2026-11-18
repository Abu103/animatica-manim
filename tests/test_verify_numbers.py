"""V1c: number grounding -- every number in caption/narration must be grounded.

Grounding sources (design 5.2): the beat's own params and fact values, the
params and fact values of earlier beats in the same scene, and the storyboard
title. Earlier captions and narration never ground anything (the laundering
case). Every expected value below is fixed by the rules, not assumed.
"""
from __future__ import annotations

import json
from pathlib import Path

from animatica.components.registry import default_registry
from animatica.storyboard.models import Beat, Scene, Storyboard
from animatica.verify.numbers import check_numbers

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "verify" / "fourier_2026_11_16.json"


def _sb(*beats, title="t"):
    return Storyboard(title=title, scenes=[Scene(beats=list(beats))])


def _beat(component, params, caption="", narration=""):
    return Beat(component=component, params=params, caption=caption, narration=narration)


def test_percent_grounded_by_the_same_param():
    sb = _sb(_beat("stat_callout", {"value": "12%", "label": "growth"}, caption="grew 12%"))
    assert check_numbers(sb, default_registry()) == []


def test_ungrounded_percent_is_an_error_on_the_caption():
    sb = _sb(_beat("stat_callout", {"value": "12%", "label": "growth"}, caption="grew 40%"))
    findings = check_numbers(sb, default_registry())
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "error"
    assert f.field == "caption"
    assert f.beat == (0, 0)
    assert "40" in f.message
    assert "caption" in f.message


def test_earlier_params_ground_but_earlier_captions_do_not():
    # Beat 0 says 40 in its caption and its own params: grounded...
    beat0 = _beat("stat_callout", {"value": "40", "label": "users"}, caption="grew 40%")
    # ...and the next beat's own params carrying 40 ground its caption too.
    grounded = _beat("stat_callout", {"value": "40", "label": "users"}, caption="still 40%")
    assert check_numbers(_sb(beat0, grounded), default_registry()) == []
    # Now beat 0's params carry nothing: the caption invention is flagged
    # where it happens, and since the number only ever appeared in a caption,
    # the repeat is still a finding (the laundering case).
    beat0 = _beat("stat_callout", {"value": "abc", "label": "users"}, caption="grew 40%")
    laundered = _beat("stat_callout", {"value": "def", "label": "users"}, caption="still 40%")
    findings = check_numbers(_sb(beat0, laundered), default_registry())
    assert [f.beat for f in findings] == [(0, 0), (0, 1)]
    assert all(f.field == "caption" and f.severity == "error" for f in findings)


def test_two_peaks_is_free_but_three_peaks_is_checked():
    # bar_chart [2, 8, 4]: facts total 14, extrema 8 and 2 -- no value near 3.
    params = {"title": "t", "labels": ["A", "B", "C"], "values": [2, 8, 4]}
    free = _sb(_beat("bar_chart", params, caption="the chart has two peaks"))
    assert check_numbers(free, default_registry()) == []
    flagged = _sb(_beat("bar_chart", params, caption="the chart has three peaks"))
    findings = check_numbers(flagged, default_registry())
    assert len(findings) == 1 and "three" in findings[0].message


def test_thousands_separator_matches():
    grounded = _sb(_beat("stat_callout", {"value": "1,234", "label": "users"},
                         caption="1,234 users joined"))
    assert check_numbers(grounded, default_registry()) == []
    off = _sb(_beat("stat_callout", {"value": "1,234", "label": "users"},
                    caption="1,233 users joined"))
    findings = check_numbers(off, default_registry())
    assert len(findings) == 1 and "1233" in findings[0].message


def test_bar_chart_total_fact_grounded():
    params = {"title": "t", "labels": ["A", "B", "C"], "values": [2, 8, 4]}
    ok = _sb(_beat("bar_chart", params, caption="14 in total"))
    assert check_numbers(ok, default_registry()) == []
    wrong = _sb(_beat("bar_chart", params, caption="15 in total"))
    findings = check_numbers(wrong, default_registry())
    assert len(findings) == 1 and "15" in findings[0].message


def test_percent_matches_a_fraction_source():
    # 12% is grounded by a source of 12 or of 0.12 (design 5.2).
    sb = _sb(_beat("stat_callout", {"value": "0.12", "label": "share"}, caption="grew 12%"))
    assert check_numbers(sb, default_registry()) == []


def test_word_number_grounded_by_multiplier_param():
    # "1M" grounds 1000000, so the word "million" mid-sentence is checked
    # (not skipped as a sentence-opening count or a number compound).
    sb = _sb(_beat("stat_callout", {"value": "1M", "label": "users"},
                   caption="the value is a million users"))
    assert check_numbers(sb, default_registry()) == []


def test_numbers_inside_param_strings_ground():
    sb = _sb(_beat("diagram", {"nodes": ["Frequency 2"], "edges": [["a", "b"]]},
                   caption="shows 2 waves"))
    assert check_numbers(sb, default_registry()) == []


def test_title_grounded():
    # "three" is mid-sentence here, so this tests the title as a real source
    # rather than the sentence-opening count exemption.
    sb = _sb(_beat("title_card", {"title": "Chapter 3", "subtitle": ""},
                   caption="the story has three steps"), title="Chapter 3")
    assert check_numbers(sb, default_registry()) == []


def test_decimals_round_to_the_written_precision():
    sb = _sb(_beat("graph", {"fn": "sin(x)", "x_range": [0, 3.14159], "y_range": [-2, 2]},
                   caption="at 3.14 radians"))
    assert check_numbers(sb, default_registry()) == []


def test_numbers_glued_to_words_are_never_flagged():
    sb = _sb(_beat("title_card", {"title": "3D shapes", "subtitle": ""},
                   caption="the 2nd step, in 3D"))
    assert check_numbers(sb, default_registry()) == []


def test_narration_is_checked_with_its_own_field():
    sb = _sb(_beat("stat_callout", {"value": "12%", "label": "growth"},
                   caption="grew 12%", narration="by 40 points"))
    findings = check_numbers(sb, default_registry())
    assert len(findings) == 1
    assert findings[0].field == "narration"
    assert "40" in findings[0].message


def test_fourier_fixture_recorded():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sb = Storyboard.model_validate(data)
    # Recorded 2026-11-17, from the owner export 20-storyboard.json: the
    # captions carry no bare digits ("two" is a free word), so grounding
    # reports no findings; V1d's domain rule is what flags this storyboard.
    findings = check_numbers(sb, default_registry())
    assert findings == []


def test_shipped_corpus_has_zero_findings():
    # A finding on a shipped example is a false positive: fix the rule,
    # not the corpus.
    roots = [Path("tests/conformance"), Path("docs/gallery")]
    findings = []
    storyboards = 0
    for root in roots:
        for path in sorted(root.glob("*.json")):
            try:
                sb = Storyboard.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            storyboards += 1
            findings.extend(check_numbers(sb, default_registry()))
    assert storyboards > 10, "the corpus walk found no storyboards"
    assert findings == []

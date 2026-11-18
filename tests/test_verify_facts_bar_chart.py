"""V1b-1: bar_chart facts are computed from the same data play() draws.

The numbers below are hand-computed from the labels and values in each test;
nothing here calls Manim. Design 5.1: facts and drawing share one pure data
function, so they cannot drift apart.
"""
from __future__ import annotations

from animatica.components.bar_chart import BarChart, _data
from animatica.components.registry import default_registry
from animatica.storyboard.models import Beat
from animatica.verify.facts import Fact, facts_for


def _facts(labels, values):
    return BarChart().facts(BarChart.Params(title="t", labels=labels, values=values))


def _one(facts, kind):
    found = [f for f in facts if f.kind == kind]
    assert len(found) == 1, f"expected exactly one {kind!r} fact, got {found}"
    return found[0]


def test_bar_chart_facts_for_three_bars():
    facts = _facts(["A", "B", "C"], [2, 8, 4])

    assert _one(facts, "total").value == 14.0
    assert _one(facts, "total").subject == "bars"

    largest, smallest = [f for f in facts if f.kind == "extremum"]
    assert largest.value == ("B", 8.0)
    assert "largest bar is B at 8" in largest.text
    assert smallest.value == ("A", 2.0)
    assert "smallest bar is A at 2" in smallest.text
    assert _one(facts, "ratio").value == 4.0
    assert [f.value for f in facts if f.kind == "value"] == [
        ("A", 2.0), ("B", 8.0), ("C", 4.0)
    ]
    assert BarChart.domain == "plain axes"


def test_zero_value_has_no_ratio():
    facts = _facts(["A", "B"], [0, 4])
    assert not [f for f in facts if f.kind == "ratio"]
    assert [f.value for f in facts if f.kind == "extremum"] == [
        ("B", 4.0), ("A", 0.0)
    ]


def test_one_bar_has_ratio_one():
    facts = _facts(["Only"], [5])
    assert _one(facts, "total").value == 5.0
    assert [f.value for f in facts if f.kind == "extremum"] == [
        ("Only", 5.0), ("Only", 5.0)
    ]
    assert _one(facts, "ratio").value == 1.0


def test_ties_go_to_the_first_label():
    facts = _facts(["A", "B"], [8, 8])
    assert [f.value for f in facts if f.kind == "extremum"] == [
        ("A", 8.0), ("A", 8.0)
    ]
    assert _one(facts, "ratio").value == 1.0


def test_facts_agree_with_the_data_the_drawing_uses():
    p = BarChart.Params(title="t", labels=["A", "B", "C"], values=[3, 5, 2])
    data = _data(p)
    assert data == [("A", 3.0), ("B", 5.0), ("C", 2.0)]

    facts = BarChart().facts(p)
    assert _one(facts, "total").value == sum(v for _, v in data)
    assert [f.value for f in facts if f.kind == "value"] == data
    largest, smallest = [f for f in facts if f.kind == "extremum"]
    assert largest.value == max(data, key=lambda pair: pair[1])
    assert smallest.value == min(data, key=lambda pair: pair[1])


def test_fact_texts_use_the_shared_plain_number_formatter():
    # f"{v:g}" writes these totals as 3.73457e+06 / 2.5e+06. Fact texts must
    # come from verify.facts.format_number: full digits, no exponent.
    facts = _facts(["A", "B"], [1234567, 2500000])
    assert "3734567" in _one(facts, "total").text
    largest = [f for f in facts if f.kind == "extremum" and "largest" in f.text][0]
    assert "2500000" in largest.text
    assert all("e+" not in f.text for f in facts)


def test_facts_for_a_bar_chart_beat():
    params = {"title": "t", "labels": ["A", "B", "C"], "values": [2, 8, 4]}
    beat = Beat(component="bar_chart", params=params)
    facts = facts_for(default_registry(), beat)
    assert facts == BarChart().facts(BarChart.Params(**params))
    assert facts and all(isinstance(f, Fact) for f in facts)

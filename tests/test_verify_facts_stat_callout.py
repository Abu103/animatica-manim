"""V1b-2: parse_number and stat_callout facts, no Manim.

Every expected value below is hand-computed from the rules in card V1b:
optional sign and currency, grouped thousands, decimals, %, x, k/M/B.
Exponents and word multipliers are deliberately not supported.
"""
from __future__ import annotations

import pytest

from animatica.components.registry import default_registry
from animatica.components.stat_callout import StatCallout
from animatica.storyboard.models import Beat
from animatica.verify.facts import Fact, facts_for, parse_number


@pytest.mark.parametrize("text,expected", [
    ("2.5M", 2500000.0),
    ("12%", 12.0),
    ("1,234", 1234.0),
    ("$1,234.50", 1234.5),
    ("-5", -5.0),
    ("3x", 3.0),
    ("1.2k", 1200.0),
    ("3B", 3e9),
    ("+€7", 7.0),
    ("₹5", 5.0),
])
def test_parse_number_accepts_supported_forms(text, expected):
    assert parse_number(text) == expected


@pytest.mark.parametrize("text", [
    "abc", "", "12 million", "1e3", "1-2", "12 USD",
    "%5", "--5", "~5",  # only $ € £ ¥ ₹ may occupy the currency slot
])
def test_parse_number_rejects_everything_else(text):
    # "1e3" is an exponent, which we do not support: it must not become 1000.
    assert parse_number(text) is None


def test_stat_callout_facts_for_a_parsed_value():
    p = StatCallout.Params(value="2.5M", label="users")
    facts = StatCallout().facts(p)
    assert len(facts) == 1
    fact = facts[0]
    assert isinstance(fact, Fact)
    assert (fact.kind, fact.subject, fact.value) == ("value", "value", 2500000.0)
    assert "headline value is 2500000" in fact.text
    assert StatCallout.domain == ""


def test_stat_callout_without_a_number_has_no_facts():
    p = StatCallout.Params(value="abc", label="users")
    assert StatCallout().facts(p) == []


def test_facts_for_a_stat_callout_beat():
    params = {"value": "1,234", "label": "users"}
    beat = Beat(component="stat_callout", params=params)
    facts = facts_for(default_registry(), beat)
    assert len(facts) == 1
    assert facts[0].value == 1234.0

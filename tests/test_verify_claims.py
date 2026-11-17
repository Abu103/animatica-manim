"""V1d: the domain rule and the small claim-pattern table (design 5.3).

Patterns run only against the fact kind they name: the peak-count pattern
only sees kind-``peak`` facts (none exist before signal_spectrum, V3), the
largest-bar pattern only sees bar_chart extremum facts, the sorted warning
only sees array_viz ``sorted`` facts. A graph's time-domain maxima are
``extremum`` facts and never feed peak counting.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from animatica.components.base import Component
from animatica.components.graph import Graph
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.storyboard.models import Beat, Scene, Storyboard
from animatica.verify.claims import check_claims, unchecked_sentences
from animatica.verify.facts import Fact

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "verify" / "fourier_2026_11_16.json"

GRAPH = {"fn": "sin(x)", "x_range": [0, 6.28], "y_range": [-2, 2]}


class _FakeSpectrum(Component):
    """Hand-built stand-in: two kind-"peak" facts, like signal_spectrum will emit."""

    name: ClassVar[str] = "fake_spectrum"

    class Params(BaseModel):
        pass

    def duration(self, p: BaseModel) -> float:
        return 1.0

    def play(self, scene, p, colors) -> None:
        raise NotImplementedError

    def fallback_text(self, p: BaseModel) -> str:
        return ""

    def facts(self, p: BaseModel) -> list[Fact]:
        return [
            Fact("peak", "signal", (1, 1.0), "peak at 1 cycle per window"),
            Fact("peak", "signal", (2, 0.5), "peak at 2 cycles per window"),
        ]


class _FakeFrequency(Component):
    """A frequency-capable component, to check the message tail flips."""

    name: ClassVar[str] = "fake_frequency"
    domain: ClassVar[str] = "frequency"

    class Params(BaseModel):
        pass

    def duration(self, p: BaseModel) -> float:
        return 1.0

    def play(self, scene, p, colors) -> None:
        raise NotImplementedError

    def fallback_text(self, p: BaseModel) -> str:
        return ""


def _sb(*beats):
    return Storyboard(title="t", scenes=[Scene(beats=list(beats))])


def _beat(component, params, caption="", narration=""):
    return Beat(component=component, params=params, caption=caption, narration=narration)


def test_domain_rule_flags_graph_caption_and_narration():
    sb = _sb(_beat("graph", GRAPH, caption="the frequency domain",
                   narration="it becomes a spectrum"))
    findings = check_claims(sb, default_registry())
    assert [(f.field, f.severity, f.beat) for f in findings] == [
        ("caption", "error", (0, 0)), ("narration", "error", (0, 0)),
    ]
    assert "frequency domain" in findings[0].message
    assert "draws plain axes" in findings[0].message
    # V3b registers signal_spectrum, so the tail now points to it (owner decision 2).
    assert "use signal_spectrum" in findings[0].message


def test_domain_rule_covers_every_spectrum_wording():
    for text in ["frequency domain", "frequency spectrum", "the spectrum",
                 "a spectral view", "power spectrum"]:
        sb = _sb(_beat("graph", GRAPH, caption=text))
        findings = check_claims(sb, default_registry())
        assert len(findings) == 1, text
        # The message quotes the matched wording (a substring of the text).
        assert any(word in findings[0].message for word in text.split()), text


def test_title_card_is_not_checked():
    sb = _sb(_beat("title_card", {"title": "t", "subtitle": ""}, caption="frequency domain"))
    assert check_claims(sb, default_registry()) == []


def test_message_tail_changes_when_a_frequency_component_exists():
    reg = ComponentRegistry()
    reg.register(Graph)
    reg.register(_FakeFrequency)
    sb = _sb(_beat("graph", GRAPH, caption="frequency domain"))
    findings = check_claims(sb, reg)
    assert len(findings) == 1
    assert "use signal_spectrum" in findings[0].message


def test_two_peaks_over_a_graph_is_never_a_peak_count_error():
    # The graph beat's maxima are kind-"extremum" facts, not kind-"peak":
    # the peak-count pattern only runs on peak facts (signal_spectrum, V3).
    # Time-domain maxima are legitimate to mention, and three shallow
    # maxima make a count claim noisy -- so the pattern stays off for graph.
    p = {"fn": "sin(x)+0.5*sin(3*x)", "x_range": [0, 6.28], "y_range": [-2, 2]}
    sb = _sb(_beat("graph", p, caption="two peaks in the wave",
                   narration="three maxima appear"))
    assert check_claims(sb, default_registry()) == []


def test_peak_count_against_peak_facts():
    reg = ComponentRegistry()
    reg.register(_FakeSpectrum)
    ok = _sb(_beat("fake_spectrum", {}, caption="two peaks"))
    assert check_claims(ok, reg) == []
    wrong = _sb(_beat("fake_spectrum", {}, caption="three peaks",
                      narration="five peaks total"))
    findings = check_claims(wrong, reg)
    assert [f.field for f in findings] == ["caption", "narration"]
    assert all(f.severity == "error" for f in findings)
    assert "the code computed 2 peaks" in findings[0].message
    digits = _sb(_beat("fake_spectrum", {}, caption="3 peaks"))
    assert len(check_claims(digits, reg)) == 1


BAR = {"title": "t", "labels": ["Q1", "Q2", "Q3"], "values": [2, 8, 4]}


def test_largest_bar_with_a_named_label():
    ok = _sb(_beat("bar_chart", BAR, caption="the largest bar is Q2 at 8"))
    assert check_claims(ok, default_registry()) == []
    wrong = _sb(_beat("bar_chart", BAR, caption="the largest bar is Q1"))
    findings = check_claims(wrong, default_registry())
    assert len(findings) == 1 and findings[0].severity == "error"
    assert "Q1" in findings[0].message and "Q2" in findings[0].message


def test_largest_bar_without_a_label_is_not_checked():
    sb = _sb(_beat("bar_chart", BAR, caption="the tallest bar stands out"))
    assert check_claims(sb, default_registry()) == []


def test_sorted_warn_only_when_the_final_state_is_not_sorted():
    unsorted_params = {"title": "t", "values": [3, 1, 2]}
    sb = _sb(_beat("array_viz", unsorted_params, caption="the array is sorted"))
    findings = check_claims(sb, default_registry())
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "not sorted" in findings[0].message

    sorted_params = {"title": "t", "values": [1, 2, 3]}
    ok = _sb(_beat("array_viz", sorted_params, caption="the array is sorted"))
    assert check_claims(ok, default_registry()) == []


def test_fourier_fixture_domain_error_and_the_known_gap():
    sb = Storyboard.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    findings = check_claims(sb, default_registry())
    # The graph beat (scene 0, beat 3) says "Frequency domain" in caption and
    # narration: both are domain-rule errors.
    assert [(f.beat, f.field) for f in findings] == [
        ((0, 3), "caption"), ((0, 3), "narration"),
    ]
    # The array_viz "Superposition" beat (beat 2) claims "Two waves add into
    # one signal". No listed pattern or fact says that 1 0 -1 0 ... is not
    # two waves adding up: this is the known gap of design 5.3, and nothing
    # may be invented to catch it here.
    assert not [f for f in findings if f.beat[1] == 2]


def test_unchecked_sentences_are_the_ones_no_rule_looked_at():
    sb = _sb(
        _beat("graph", GRAPH, caption="frequency domain. A gentle slope."),
        _beat("title_card", {"title": "t", "subtitle": ""},
              caption="hello world"),
    )
    unchecked = unchecked_sentences(sb, default_registry())
    sentences = [s for _, s in unchecked]
    assert "A gentle slope." in sentences
    assert "hello world" in sentences
    assert "frequency domain" not in sentences


def test_claims_are_idempotent():
    sb = _sb(_beat("graph", GRAPH, caption="frequency domain"))
    assert check_claims(sb, default_registry()) == check_claims(sb, default_registry())

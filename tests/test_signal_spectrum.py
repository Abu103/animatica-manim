"""V3a: signal_spectrum pure data, validation and facts (no drawing).

The numbers here were computed with numpy from the design's own formula
(N = 256, integer cycle frequencies, so no spectral leakage).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from animatica.components.graph import Graph
from animatica.components.registry import ComponentRegistry
from animatica.components.signal_spectrum import SignalSpectrum, _data
from animatica.storyboard.models import Beat, Scene, Storyboard
from animatica.verify.claims import check_claims
from animatica.verify.facts import facts_for

TWO_TONES = {
    "title": "Two tones",
    "waves": [{"freq": 3, "amp": 1.0}, {"freq": 5, "amp": 0.5}],
}
PHASED_SINGLE = {
    "title": "One tone",
    "waves": [{"freq": 4, "amp": 1.0, "phase": 0.5}],
}
PHASED_TWO = {
    "title": "Two shifted tones",
    "waves": [{"freq": 2, "amp": 2.0, "phase": -1.0},
              {"freq": 7, "amp": 1.0, "phase": 3.0}],
}


def _params(d: dict):
    return SignalSpectrum.Params.model_validate(d)


def _facts(d: dict):
    return SignalSpectrum().facts(_params(d))


def _of_kind(facts, kind: str):
    return [f for f in facts if f.kind == kind]


def test_two_tones_peaks_range_and_facts():
    data = _data(_params(TWO_TONES))
    assert data.peaks == [3, 5]
    assert data.freqs[0] == 0 and data.freqs[-1] == 128
    facts = _facts(TWO_TONES)
    peaks = _of_kind(facts, "peak")
    assert [f.value for f in peaks] == [(3, 1.0), (5, 0.5)]
    assert peaks[0].text == "spectrum has a peak at 3 cycles per window with amplitude 1.0"
    assert _of_kind(facts, "range")[0].value == (-1.386, 1.386)
    domain = _of_kind(facts, "domain")
    assert len(domain) == 1 and domain[0].value == "frequency"


def test_phase_shifted_single_wave():
    assert _data(_params(PHASED_SINGLE)).peaks == [4]
    assert [f.value for f in _of_kind(_facts(PHASED_SINGLE), "peak")] == [(4, 1.0)]
    assert _of_kind(_facts(PHASED_SINGLE), "range")[0].value == (-1.0, 1.0)


def test_two_phase_shifted_waves():
    assert _data(_params(PHASED_TWO)).peaks == [2, 7]
    assert [f.value for f in _of_kind(_facts(PHASED_TWO), "peak")] == [(2, 2.0), (7, 1.0)]
    assert _of_kind(_facts(PHASED_TWO), "range")[0].value == (-2.977, 2.928)


@pytest.mark.parametrize("fixture", [TWO_TONES, PHASED_SINGLE, PHASED_TWO])
def test_facts_agree_with_data(fixture):
    p = _params(fixture)
    data = _data(p)
    peak_facts = _of_kind(SignalSpectrum().facts(p), "peak")
    assert [f.value[0] for f in peak_facts] == data.peaks
    assert [f.value[1] for f in peak_facts] == [round(float(data.mags[k]), 3) for k in data.peaks]
    assert data.peaks == [w.freq for w in p.waves]
    assert facts_for(_registry(), _beat("signal_spectrum", fixture, caption="")) == SignalSpectrum().facts(p)


def test_duplicate_frequencies_rejected():
    bad = {"title": "t", "waves": [{"freq": 3, "amp": 1.0}, {"freq": 3, "amp": 0.5}]}
    with pytest.raises(ValidationError, match="distinct"):
        _params(bad)


def test_five_waves_rejected():
    bad = {"title": "t", "waves": [{"freq": f, "amp": 1.0} for f in range(1, 6)]}
    with pytest.raises(ValidationError):
        _params(bad)


@pytest.mark.parametrize("freq", [0, 41])
def test_frequency_out_of_range_rejected(freq):
    bad = {"title": "t", "waves": [{"freq": freq, "amp": 1.0}]}
    with pytest.raises(ValidationError):
        _params(bad)


def test_phase_and_show_defaults_and_duration():
    p = _params({"title": "t", "waves": [{"freq": 3, "amp": 1.0}]})
    assert p.waves[0].phase == 0.0 and p.show == "both"
    assert SignalSpectrum().duration(p) == 5.0
    one_panel = _params({"title": "t", "waves": [{"freq": 3, "amp": 1.0}], "show": "time"})
    assert SignalSpectrum().duration(one_panel) == 3.5


def _beat(component: str, params: dict, caption: str) -> Beat:
    return Beat(component=component, params=params, caption=caption, narration="")


def _registry() -> ComponentRegistry:
    reg = ComponentRegistry()
    reg.register(Graph)
    reg.register(SignalSpectrum)
    return reg


def _sb(component: str, params: dict, caption: str) -> Storyboard:
    return Storyboard(title="t", scenes=[Scene(beats=[_beat(component, params, caption)])])


# --- V1d's peak-count and domain rules, now exercised against the real component (owner decision 2) ---

def test_real_spectrum_two_peaks_claim_is_not_flagged():
    findings = check_claims(_sb("signal_spectrum", TWO_TONES, "two peaks"), _registry())
    assert findings == []


def test_real_spectrum_three_peaks_claim_is_an_error():
    findings = check_claims(_sb("signal_spectrum", TWO_TONES, "three peaks"), _registry())
    assert len(findings) == 1
    assert findings[0].severity == "error" and findings[0].field == "caption"
    assert "the code computed 2 peaks" in findings[0].message


def test_frequency_domain_over_real_spectrum_is_not_flagged():
    sb = _sb("signal_spectrum", TWO_TONES, "the frequency domain has two peaks")
    assert check_claims(sb, _registry()) == []


def test_graph_beat_message_tail_points_to_signal_spectrum():
    graph = {"fn": "sin(x)", "x_range": [0, 6.28], "y_range": [-2, 2]}
    findings = check_claims(_sb("graph", graph, "frequency domain"), _registry())
    assert len(findings) == 1
    assert "use signal_spectrum" in findings[0].message
